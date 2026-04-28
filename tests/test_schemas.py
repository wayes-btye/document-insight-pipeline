"""Schema contract tests. Validate that Pydantic models accept/reject the right shapes."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas import (
    Action,
    AggregatedFindings,
    Insight,
    Opportunity,
    PerDocExtract,
    Risk,
    SummaryReport,
    Theme,
)


def _good_findings() -> AggregatedFindings:
    return AggregatedFindings(
        themes=[Theme(name="x", description="y", citations=["a.txt"], salience="high")],
        insights=[Insight(statement="x", citations=["a.txt"], confidence="medium")],
        risks=[Risk(statement="x", likelihood="high", impact="low", citations=["a.txt"])],
        opportunities=[Opportunity(statement="x", citations=["a.txt"])],
        actions=[Action(description="x", owner="alice", timeframe="now", citations=["a.txt"])],
    )


def test_theme_requires_at_least_one_citation():
    with pytest.raises(ValidationError):
        Theme(name="x", description="y", citations=[], salience="high")


def test_risk_requires_at_least_one_citation():
    with pytest.raises(ValidationError):
        Risk(statement="x", likelihood="high", impact="high", citations=[])


def test_action_requires_at_least_one_citation():
    with pytest.raises(ValidationError):
        Action(description="x", owner=None, timeframe=None, citations=[])


def test_per_doc_extract_accepts_empty_lists():
    extract = PerDocExtract(
        source_file="x.txt",
        themes=[],
        insights=[],
        risks=[],
        opportunities=[],
        actions=[],
        notes=None,
    )
    assert extract.source_file == "x.txt"


def test_summary_report_rejects_unknown_fields():
    """extra='forbid' must reject unknown keys (typo guard)."""
    with pytest.raises(ValidationError):
        SummaryReport.model_validate({
            "executive_summary": "x",
            "findings": _good_findings().model_dump(),
            "assumptions": ["x"],
            "limitations": ["x"],
            "metadata": {
                "docs_processed": 1, "model": "x", "timestamp_utc": "x",
                "total_tokens_input": 0, "total_tokens_output": 0,
                "estimated_cost_usd": 0.0, "duration_seconds": 0.0,
            },
            "executive_summery": "typo here",  # noqa: SC100 (deliberate typo)
        })


def test_summary_report_rejects_invalid_salience():
    with pytest.raises(ValidationError):
        Theme(name="x", description="y", citations=["a"], salience="urgent")  # type: ignore[arg-type]
