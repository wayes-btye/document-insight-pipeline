"""End-to-end pipeline test against the mock provider.

The whole map → reduce → synthesise → assemble flow must produce a schema-valid
SummaryReport and pass Tier 1 hard constraints. Tier 2 capability is not
asserted here — the mock is intentionally simplistic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.grader import discover_valid_filenames, grade, load_manifest, load_thresholds
from src.cost import CostTracker
from src.pipeline import run_pipeline
from src.providers.mock import MockProvider

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.asyncio
async def test_mock_pipeline_produces_valid_report_and_passes_tier_1(tmp_path):
    provider = MockProvider()
    cost = CostTracker(prices={}, model=provider.model)
    report = await run_pipeline(
        provider=provider,
        input_dir=REPO_ROOT / "input_docs",
        concurrency=10,
        cost_tracker=cost,
    )

    assert report.metadata.docs_processed == 101
    assert report.executive_summary
    assert len(report.findings.themes) >= 1
    assert len(report.findings.insights) >= 1
    assert len(report.findings.risks) >= 1
    assert len(report.findings.opportunities) >= 1
    assert len(report.findings.actions) >= 1
    assert len(report.assumptions) >= 1
    assert len(report.limitations) >= 1

    # Run through the eval and assert Tier 1 is fully PASS (mock should never hallucinate
    # citations because it only emits filenames it has seen).
    raw = report.model_dump()
    manifest = load_manifest(REPO_ROOT / "eval" / "manifest.yaml")
    thresholds = load_thresholds(REPO_ROOT / "eval" / "thresholds.yaml")
    valid = discover_valid_filenames(REPO_ROOT / "input_docs")
    tiers, parsed = grade(raw, manifest, thresholds, valid)
    assert parsed is not None
    tier1 = tiers[0]
    failures = [(m.name, m.value, m.threshold) for m in tier1.metrics if not m.passed]
    assert not failures, f"mock pipeline should pass Tier 1 hard constraints; got: {failures}"


@pytest.mark.asyncio
async def test_mock_pipeline_strips_unknown_citations(tmp_path):
    """Pipeline must filter citations to filenames not in input_dir before they reach output."""
    # Tiny corpus
    d = tmp_path / "in"
    d.mkdir()
    (d / "a.txt").write_text("renewal pricing pressure across the portfolio")
    (d / "b.txt").write_text("Apex aggressive pricing competitor")

    provider = MockProvider()
    report = await run_pipeline(provider=provider, input_dir=d, concurrency=2)
    seen_files = {"a.txt", "b.txt"}
    for theme in report.findings.themes:
        for cite in theme.citations:
            assert cite in seen_files, f"theme cited unknown file: {cite}"
