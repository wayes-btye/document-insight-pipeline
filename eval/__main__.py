"""CLI: python -m eval --report path [options]

Runs the eval framework against a SummaryReport JSON and prints per-tier
results. Exits non-zero if any metric fails when --strict is set.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from eval.grader import (
    discover_valid_filenames,
    grade,
    load_manifest,
    load_report,
    load_thresholds,
)
from eval.metrics import TierResult
from src.schemas import SummaryReport

REPO_ROOT = Path(__file__).resolve().parent.parent


def _format_tier(t: TierResult) -> str:
    lines = [f"\nTier {t.tier} — {t.name}  ({'PASS' if t.passed else 'FAIL'})"]
    for m in t.metrics:
        mark = "OK " if m.passed else "XX "
        lines.append(f"  {mark} {m.name:<40s} {m.value:.3f}  {m.operator} {m.threshold}")
        if m.details and not m.passed:
            for line in str(m.details).splitlines():
                lines.append(f"        {line}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m eval", description="Grade a SummaryReport against the sealed manifest."
    )
    p.add_argument("--report", required=True, type=Path, help="Path to summary_report.json")
    p.add_argument(
        "--input-dir",
        type=Path,
        default=REPO_ROOT / "input_docs",
        help="Path to the corpus directory (for citation hallucination check)",
    )
    p.add_argument("--manifest", type=Path, default=REPO_ROOT / "eval" / "manifest.yaml")
    p.add_argument("--thresholds", type=Path, default=REPO_ROOT / "eval" / "thresholds.yaml")
    p.add_argument(
        "--consistency-against",
        type=Path,
        default=None,
        help="Optional: a second SummaryReport JSON for run-to-run Jaccard",
    )
    p.add_argument("--strict", action="store_true", help="Exit non-zero if any metric fails")
    p.add_argument("--verbose", action="store_true", help="Show details for passing metrics too")
    args = p.parse_args(argv)

    raw_report = load_report(args.report)
    manifest = load_manifest(args.manifest)
    thresholds = load_thresholds(args.thresholds)
    valid_filenames = discover_valid_filenames(args.input_dir)

    consistency_against: SummaryReport | None = None
    if args.consistency_against:
        # Reuse parser from grader by parsing inline
        from src.schemas import SummaryReport as _SR

        with args.consistency_against.open() as f:
            import json as _json

            consistency_against = _SR.model_validate(_json.load(f))

    tiers, _parsed = grade(
        raw_report=raw_report,
        manifest=manifest,
        thresholds=thresholds,
        valid_filenames=valid_filenames,
        consistency_against=consistency_against,
    )

    print(f"Eval against: {args.report}")
    print(f"Corpus:       {args.input_dir} ({len(valid_filenames)} files)")
    print(f"Manifest:     {args.manifest}")
    overall_pass = True
    for t in tiers:
        print(_format_tier(t))
        if not t.passed:
            overall_pass = False

    print(f"\nOverall: {'PASS' if overall_pass else 'FAIL'}")

    if args.strict and not overall_pass:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
