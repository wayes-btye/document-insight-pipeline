"""Tests for the markdown / JSON output writers."""

from __future__ import annotations

import json
from pathlib import Path

from src.output import render_markdown, write_outputs
from src.schemas import (
    Action,
    AggregatedFindings,
    Insight,
    Opportunity,
    ReportMetadata,
    Risk,
    SummaryReport,
    Theme,
)


def _example_report() -> SummaryReport:
    return SummaryReport(
        executive_summary="Two patterns dominate the quarter.",
        findings=AggregatedFindings(
            themes=[Theme(name="Pricing", description="Renewals tighter.", citations=["a.txt", "b.txt"], salience="high")],
            insights=[Insight(statement="Margin compressed.", citations=["a.txt"], confidence="high")],
            risks=[Risk(statement="Churn risk.", likelihood="medium", impact="high", citations=["b.txt"])],
            opportunities=[Opportunity(statement="Upsell vector.", citations=["a.txt"])],
            actions=[Action(description="Bring forward review.", owner="Alice", timeframe="Q4", citations=["a.txt"])],
        ),
        assumptions=["Sample is representative."],
        limitations=["No buyer interviews."],
        metadata=ReportMetadata(
            docs_processed=2, model="mock", timestamp_utc="2026-04-28T00:00:00+00:00",
            total_tokens_input=100, total_tokens_output=50, estimated_cost_usd=0.001, duration_seconds=0.5,
        ),
    )


def test_markdown_contains_all_sections():
    md = render_markdown(_example_report())
    for section in (
        "# Portfolio Insight Report", "## Executive summary", "## Themes", "## Key insights",
        "## Risks", "## Opportunities", "## Recommended actions", "## Assumptions", "## Limitations",
    ):
        assert section in md, f"missing section: {section}"
    assert "`a.txt`" in md
    assert "Bring forward review." in md
    assert "owner: Alice" in md


def test_write_outputs_both_formats(tmp_path: Path):
    written = write_outputs(_example_report(), tmp_path / "report", "both")
    paths = sorted(p.name for p in written)
    assert paths == ["report.json", "report.md"]
    parsed = json.loads((tmp_path / "report.json").read_text())
    assert parsed["executive_summary"]
    assert parsed["findings"]["themes"][0]["name"] == "Pricing"


def test_write_outputs_md_only_strips_extension(tmp_path: Path):
    written = write_outputs(_example_report(), tmp_path / "report.md", "md")
    assert [p.suffix for p in written] == [".md"]
