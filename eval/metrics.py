"""Metric implementations for the three-tier evaluation framework.

Pure functions. Each takes a parsed `SummaryReport` (plus context like
manifest, valid filenames) and returns a numeric score in [0, 1].

See docs/evaluation.md for the rationale behind each metric.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from src.schemas import SummaryReport, Theme

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def _theme_text(theme: Theme) -> str:
    return _normalise(f"{theme.name} {theme.description}")


def _item_texts(report: SummaryReport) -> list[str]:
    """Concatenated text of every surfaced item, for distractor matching."""
    out: list[str] = []
    for t in report.findings.themes:
        out.append(_theme_text(t))
    for i in report.findings.insights:
        out.append(_normalise(i.statement))
    for r in report.findings.risks:
        out.append(_normalise(r.statement))
    for o in report.findings.opportunities:
        out.append(_normalise(o.statement))
    for a in report.findings.actions:
        out.append(_normalise(a.description))
    return out


def _all_citations(report: SummaryReport) -> list[str]:
    cites: list[str] = []
    for t in report.findings.themes:
        cites.extend(t.citations)
    for i in report.findings.insights:
        cites.extend(i.citations)
    for r in report.findings.risks:
        cites.extend(r.citations)
    for o in report.findings.opportunities:
        cites.extend(o.citations)
    for a in report.findings.actions:
        cites.extend(a.citations)
    return cites


def _theme_aliases(manifest_theme: dict[str, Any]) -> list[str]:
    """All searchable strings for a theme (canonical + aliases), normalised."""
    out = [_normalise(manifest_theme["canonical_name"])]
    out.extend(_normalise(a) for a in manifest_theme.get("aliases", []) or [])
    return [c for c in out if len(c) >= 5]


def _matches(text: str, candidates: Iterable[str]) -> bool:
    """True if any candidate appears as a substring of text (or vice versa)."""
    for c in candidates:
        if not c:
            continue
        if c in text or text in c:
            return True
    return False


def _surfaced_theme_ids(report: SummaryReport, manifest_themes: list[dict[str, Any]]) -> set[str]:
    """Set of manifest theme IDs that the report surfaces (matched via name+description)."""
    surfaced: set[str] = set()
    for r_theme in report.findings.themes:
        text = _theme_text(r_theme)
        for m_theme in manifest_themes:
            if _matches(text, _theme_aliases(m_theme)):
                surfaced.add(m_theme["id"])
    return surfaced


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class MetricResult:
    name: str
    value: float
    threshold: float
    operator: str  # ">=", "<=", "=="
    passed: bool
    details: str = ""


@dataclass
class TierResult:
    tier: int
    name: str
    metrics: list[MetricResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(m.passed for m in self.metrics)


# ---------------------------------------------------------------------------
# Tier 1: hard constraints
# ---------------------------------------------------------------------------


def schema_validity(raw_report: dict[str, Any] | str) -> tuple[float, SummaryReport | None, str]:
    """Try to parse raw report as SummaryReport. Returns (score, parsed-or-none, error-message)."""
    try:
        if isinstance(raw_report, str):
            parsed = SummaryReport.model_validate_json(raw_report)
        else:
            parsed = SummaryReport.model_validate(raw_report)
        return 1.0, parsed, ""
    except Exception as exc:
        return 0.0, None, str(exc)


def citation_hallucination_rate(report: SummaryReport, valid_filenames: set[str]) -> tuple[float, list[str]]:
    """Fraction of citations that reference filenames not present in input dir.

    Returns (rate, list_of_hallucinated_filenames).
    """
    cites = _all_citations(report)
    if not cites:
        return 0.0, []
    hallucinated = [c for c in cites if c not in valid_filenames]
    return len(hallucinated) / len(cites), sorted(set(hallucinated))


def required_fields_populated(report: SummaryReport) -> float:
    """Required scalar fields are non-empty strings.

    Pydantic strict mode covers presence; this catches cases where a field is
    present but blank (empty string, whitespace-only).
    """
    checks = [
        bool(report.executive_summary.strip()),
        bool(report.metadata.model.strip()),
        bool(report.metadata.timestamp_utc.strip()),
    ]
    return sum(checks) / len(checks)


def report_section_completeness(report: SummaryReport) -> float:
    """All eight report sections from the brief are present and non-empty."""
    sections = {
        "executive_summary": bool(report.executive_summary.strip()),
        "themes": len(report.findings.themes) > 0,
        "insights": len(report.findings.insights) > 0,
        "risks": len(report.findings.risks) > 0,
        "opportunities": len(report.findings.opportunities) > 0,
        "actions": len(report.findings.actions) > 0,
        "assumptions": len(report.assumptions) > 0,
        "limitations": len(report.limitations) > 0,
    }
    return sum(sections.values()) / len(sections)


# ---------------------------------------------------------------------------
# Tier 2: synthetic-distribution capability
# ---------------------------------------------------------------------------


def theme_recall(
    report: SummaryReport,
    manifest_themes: list[dict[str, Any]],
    salience: str,
) -> tuple[float, list[str], list[str]]:
    """Fraction of manifest themes at the given salience that the report surfaced.

    Returns (recall, surfaced_ids, missed_ids).
    """
    candidates = [t for t in manifest_themes if t.get("salience") == salience]
    if not candidates:
        return 1.0, [], []
    surfaced = _surfaced_theme_ids(report, candidates)
    candidate_ids = {t["id"] for t in candidates}
    missed = sorted(candidate_ids - surfaced)
    return len(surfaced) / len(candidate_ids), sorted(surfaced), missed


def citation_precision(
    report: SummaryReport,
    manifest_themes: list[dict[str, Any]],
    pure_noise: set[str],
) -> tuple[float, dict[str, dict[str, Any]]]:
    """For each report theme matched to a manifest theme, what fraction of its
    citations appear in that theme's expected_docs?

    Citations to pure_noise files always count as imprecise (no theme owns them).
    Macro-average across matched themes.
    """
    per_theme: dict[str, dict[str, Any]] = {}
    precisions: list[float] = []
    for r_theme in report.findings.themes:
        text = _theme_text(r_theme)
        matched = [m for m in manifest_themes if _matches(text, _theme_aliases(m))]
        if not matched:
            continue  # unmatched themes don't contribute to precision (recall covers them)
        # Use the BEST-matching manifest theme: most aliases hit
        best = max(
            matched,
            key=lambda m: sum(1 for c in _theme_aliases(m) if c in text or text in c),
        )
        expected = set(best.get("expected_docs", []))
        cites = r_theme.citations
        if not cites:
            continue
        good = [c for c in cites if c in expected and c not in pure_noise]
        bad = [c for c in cites if c not in expected or c in pure_noise]
        prec = len(good) / len(cites)
        precisions.append(prec)
        per_theme[r_theme.name] = {
            "matched_manifest_id": best["id"],
            "precision": prec,
            "good_citations": good,
            "bad_citations": bad,
        }
    if not precisions:
        return 0.0, per_theme
    return sum(precisions) / len(precisions), per_theme


def doc_coverage(report: SummaryReport, substantive_docs: set[str]) -> tuple[float, list[str]]:
    """Fraction of substantive docs cited at least once anywhere in the report.

    `substantive_docs` = union of expected_docs across all manifest themes
    (excludes distractors and pure noise).
    """
    if not substantive_docs:
        return 1.0, []
    cited = set(_all_citations(report))
    covered = substantive_docs & cited
    missed = sorted(substantive_docs - cited)
    return len(covered) / len(substantive_docs), missed


def false_positive_rate_on_distractors(
    report: SummaryReport,
    distractors: list[dict[str, Any]],
    pure_noise: set[str],
) -> tuple[float, list[str]]:
    """Fraction of report items that surface distractor content.

    A report item is a false positive if EITHER:
      - its text matches any distractor's canonical name or aliases, OR
      - any of its citations is to a pure_noise file.
    Macro across all surfaced items (themes, insights, risks, opportunities, actions).
    """
    items = _item_texts(report)
    if not items:
        return 0.0, []

    distractor_aliases: list[str] = []
    for d in distractors:
        distractor_aliases.extend(_theme_aliases(d))

    item_records: list[tuple[str, str]] = []
    for t in report.findings.themes:
        item_records.append(("theme:" + t.name, _theme_text(t)))
        if any(c in pure_noise for c in t.citations):
            pass  # caught below
    for i in report.findings.insights:
        item_records.append(("insight", _normalise(i.statement)))
    for r in report.findings.risks:
        item_records.append(("risk", _normalise(r.statement)))
    for o in report.findings.opportunities:
        item_records.append(("opportunity", _normalise(o.statement)))
    for a in report.findings.actions:
        item_records.append(("action", _normalise(a.description)))

    citations_per_item: list[list[str]] = []
    for t in report.findings.themes:
        citations_per_item.append(t.citations)
    for i in report.findings.insights:
        citations_per_item.append(i.citations)
    for r in report.findings.risks:
        citations_per_item.append(r.citations)
    for o in report.findings.opportunities:
        citations_per_item.append(o.citations)
    for a in report.findings.actions:
        citations_per_item.append(a.citations)

    fps: list[str] = []
    for (label, text), cites in zip(item_records, citations_per_item, strict=True):
        is_fp = False
        if _matches(text, distractor_aliases) or any(c in pure_noise for c in cites):
            is_fp = True
        if is_fp:
            fps.append(label)

    return len(fps) / len(item_records), fps


def consistency_jaccard(
    report_a: SummaryReport, report_b: SummaryReport, manifest_themes: list[dict[str, Any]]
) -> float:
    """Jaccard similarity between the sets of manifest theme IDs surfaced by two runs."""
    set_a = _surfaced_theme_ids(report_a, manifest_themes)
    set_b = _surfaced_theme_ids(report_b, manifest_themes)
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)
