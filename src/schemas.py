"""Pydantic models that define the tool's output contract.

Single source of truth: the extraction pipeline produces these shapes,
the LLM is asked for these shapes via response_format, and the eval harness
grades against these shapes.

Two layers:

- *Wire* schemas (`PerDocExtractPayload`, `AggregatedFindings`, `SynthesisPayload`)
  are sent to the LLM as `response_format`. They have no defaults because
  OpenAI structured outputs require every field in `required`.

- *Domain* schemas (`PerDocExtract`, `SummaryReport`) wrap the wire schemas
  with metadata that the pipeline owns (source filename, run metadata).
  These are also what the eval grader sees.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Salience = Literal["high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Map stage
# ---------------------------------------------------------------------------


class PerDocExtractPayload(_Strict):
    """What the LLM returns for one document. No source_file (we own that)."""

    themes: list[str]
    insights: list[str]
    risks: list[str]
    opportunities: list[str]
    actions: list[str]
    notes: str | None


class PerDocExtract(_Strict):
    """One document's extract, after the pipeline has pinned source_file."""

    source_file: str
    themes: list[str]
    insights: list[str]
    risks: list[str]
    opportunities: list[str]
    actions: list[str]
    notes: str | None


# ---------------------------------------------------------------------------
# Reduce stage — final shapes (also what the LLM returns for AggregatedFindings)
# ---------------------------------------------------------------------------


class Theme(_Strict):
    name: str
    description: str
    citations: list[str] = Field(min_length=1)
    salience: Salience


class Insight(_Strict):
    statement: str
    citations: list[str] = Field(min_length=1)
    confidence: Confidence | None


class Risk(_Strict):
    statement: str
    likelihood: Salience
    impact: Salience
    citations: list[str] = Field(min_length=1)


class Opportunity(_Strict):
    statement: str
    citations: list[str] = Field(min_length=1)


class Action(_Strict):
    description: str
    owner: str | None
    timeframe: str | None
    citations: list[str] = Field(min_length=1)


class AggregatedFindings(_Strict):
    themes: list[Theme]
    insights: list[Insight]
    risks: list[Risk]
    opportunities: list[Opportunity]
    actions: list[Action]


# ---------------------------------------------------------------------------
# Synthesis stage — narrative pieces the LLM produces, plus the assembled report
# ---------------------------------------------------------------------------


class SynthesisPayload(_Strict):
    """The narrative pieces the synthesis LLM call produces."""

    executive_summary: str
    assumptions: list[str]
    limitations: list[str]


class ReportMetadata(_Strict):
    docs_processed: int
    model: str
    timestamp_utc: str
    total_tokens_input: int
    total_tokens_output: int
    estimated_cost_usd: float
    duration_seconds: float


class SummaryReport(_Strict):
    """The full structured output the tool produces. Mirrors summary_report.json."""

    executive_summary: str
    findings: AggregatedFindings
    assumptions: list[str]
    limitations: list[str]
    metadata: ReportMetadata
