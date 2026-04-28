"""Eval orchestrator. Reads manifest + thresholds, runs all metrics, returns TierResults."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from eval import metrics
from eval.metrics import MetricResult, TierResult
from src.schemas import SummaryReport


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open() as f:
        loaded = yaml.safe_load(f)
    assert isinstance(loaded, dict), f"manifest must be a mapping, got {type(loaded).__name__}"
    return loaded


def load_thresholds(path: Path) -> dict[str, Any]:
    with path.open() as f:
        loaded = yaml.safe_load(f)
    assert isinstance(loaded, dict), f"thresholds must be a mapping, got {type(loaded).__name__}"
    return loaded


def load_report(path: Path) -> Any:
    """Load report as raw structure (dict). Schema validation happens in grade()."""
    with path.open() as f:
        return json.load(f)


def discover_valid_filenames(input_dir: Path) -> set[str]:
    return {p.name for p in input_dir.glob("*.txt")}


def _check(name: str, value: float, threshold: float, operator: str, details: str = "") -> MetricResult:
    if operator == ">=":
        passed = value >= threshold
    elif operator == "<=":
        passed = value <= threshold
    elif operator == "==":
        passed = value == threshold
    else:
        raise ValueError(f"unknown operator {operator!r}")
    return MetricResult(
        name=name, value=value, threshold=threshold, operator=operator, passed=passed, details=details
    )


def grade(
    raw_report: Any,
    manifest: dict[str, Any],
    thresholds: dict[str, Any],
    valid_filenames: set[str],
    consistency_against: SummaryReport | None = None,
) -> tuple[list[TierResult], SummaryReport | None]:
    """Run the eval and return per-tier results.

    If schema validation fails, Tier 1 returns one failed metric and Tier 2/3
    are skipped entirely (they cannot be computed without a parsed report).
    """
    t1_thresh = thresholds["tier_1_hard_constraints"]
    t2_thresh = thresholds["tier_2_capability"]
    manifest_themes = manifest.get("themes", []) or []
    distractors = manifest.get("distractors", []) or []
    pure_noise = set(manifest.get("pure_noise", []) or [])

    # ---- Tier 1 ----
    tier1 = TierResult(tier=1, name="hard constraints")

    schema_score, parsed, err = metrics.schema_validity(raw_report)
    tier1.metrics.append(
        _check(
            "schema_validity",
            schema_score,
            t1_thresh["schema_validity"],
            "==",
            details=err if not parsed else "",
        )
    )

    if parsed is None:
        return [tier1], None

    halluc_rate, hallucinated = metrics.citation_hallucination_rate(parsed, valid_filenames)
    tier1.metrics.append(
        _check(
            "citation_hallucination_rate",
            halluc_rate,
            t1_thresh["citation_hallucination_rate_max"],
            "<=",
            details=f"hallucinated: {hallucinated}" if hallucinated else "",
        )
    )

    req_score = metrics.required_fields_populated(parsed)
    tier1.metrics.append(
        _check("required_fields_populated", req_score, t1_thresh["required_fields_populated"], "==")
    )

    sect_score = metrics.report_section_completeness(parsed)
    tier1.metrics.append(
        _check("report_section_completeness", sect_score, t1_thresh["report_section_completeness"], "==")
    )

    # ---- Tier 2 ----
    tier2 = TierResult(tier=2, name="synthetic capability")

    for sal, key in (
        ("high", "primary_theme_recall_min"),
        ("medium", "secondary_theme_recall_min"),
        ("low", "minor_theme_recall_min"),
    ):
        recall, surfaced, missed = metrics.theme_recall(parsed, manifest_themes, sal)
        tier2.metrics.append(
            _check(
                f"{sal}_theme_recall",
                recall,
                t2_thresh[key],
                ">=",
                details=f"surfaced={surfaced} missed={missed}",
            )
        )

    cite_prec, per_theme_prec = metrics.citation_precision(parsed, manifest_themes, pure_noise)
    tier2.metrics.append(
        _check(
            "citation_precision",
            cite_prec,
            t2_thresh["citation_precision_min"],
            ">=",
            details=_format_per_theme_precision(per_theme_prec),
        )
    )

    substantive_docs: set[str] = set()
    for t in manifest_themes:
        substantive_docs.update(t.get("expected_docs", []) or [])
    cov, missed_docs = metrics.doc_coverage(parsed, substantive_docs)
    tier2.metrics.append(
        _check(
            "doc_coverage",
            cov,
            t2_thresh["doc_coverage_min"],
            ">=",
            details=f"uncited substantive docs: {len(missed_docs)} (showing 5: {missed_docs[:5]})",
        )
    )

    fp_rate, fps = metrics.false_positive_rate_on_distractors(parsed, distractors, pure_noise)
    tier2.metrics.append(
        _check(
            "false_positive_rate_on_distractors",
            fp_rate,
            t2_thresh["false_positive_rate_on_distractors_max"],
            "<=",
            details=f"false positives: {fps}" if fps else "",
        )
    )

    if consistency_against is not None:
        jac = metrics.consistency_jaccard(parsed, consistency_against, manifest_themes)
        tier2.metrics.append(_check("consistency_jaccard", jac, t2_thresh["consistency_jaccard_min"], ">="))

    return [tier1, tier2], parsed


def _format_per_theme_precision(per_theme: dict[str, dict[str, Any]]) -> str:
    if not per_theme:
        return "no themes matched a manifest entry"
    lines = []
    for name, rec in per_theme.items():
        lines.append(
            f"  {name!r} → {rec['matched_manifest_id']} prec={rec['precision']:.2f} bad={rec['bad_citations']}"
        )
    return "\n" + "\n".join(lines)
