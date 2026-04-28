"""Tests for the deterministic mock provider."""

from __future__ import annotations

import pytest

from src.providers.mock import MockProvider
from src.schemas import AggregatedFindings, PerDocExtractPayload, SynthesisPayload


@pytest.mark.asyncio
async def test_mock_extract_detects_pricing_theme():
    p = MockProvider()
    user = (
        "SOURCE_FILE: example.txt\n"
        "<<<DOCUMENT START>>>\n"
        "Karen at Lattice asked about renewal pricing. Procurement wants a discount.\n"
        "<<<DOCUMENT END>>>"
    )
    result = await p.complete_structured(system="x", user=user, response_model=PerDocExtractPayload)
    assert "Pricing pressure on renewals" in result.payload.themes


@pytest.mark.asyncio
async def test_mock_extract_admin_doc_is_mostly_empty():
    p = MockProvider()
    user = (
        "SOURCE_FILE: office.txt\n"
        "<<<DOCUMENT START>>>\n"
        "Office relocation: please box your desk by Thursday EOD. New address is Vine Street.\n"
        "<<<DOCUMENT END>>>"
    )
    result = await p.complete_structured(system="x", user=user, response_model=PerDocExtractPayload)
    # No strategic theme keywords trigger
    assert result.payload.themes == []


@pytest.mark.asyncio
async def test_mock_aggregate_counts_themes_across_docs():
    p = MockProvider()
    docs = [
        ("a.txt", "renewal pricing pressure on Crestline"),
        ("b.txt", "Apex pricing discount conversation"),
        ("c.txt", "discount requests rising in Q3"),
    ]
    for fn, body in docs:
        user = f"SOURCE_FILE: {fn}\n<<<DOCUMENT START>>>\n{body}\n<<<DOCUMENT END>>>"
        await p.complete_structured(system="x", user=user, response_model=PerDocExtractPayload)
    result = await p.complete_structured(system="x", user="", response_model=AggregatedFindings)
    findings = result.payload
    pricing = [t for t in findings.themes if "Pricing pressure" in t.name]
    assert pricing, f"expected pricing theme, got {[t.name for t in findings.themes]}"
    # All three docs surface pricing keywords
    assert set(pricing[0].citations) == {"a.txt", "b.txt", "c.txt"}


@pytest.mark.asyncio
async def test_mock_synthesis_produces_required_fields():
    p = MockProvider()
    # Seed with one doc so aggregate has something
    await p.complete_structured(
        system="x",
        user="SOURCE_FILE: a.txt\n<<<DOCUMENT START>>>\nrenewal pricing\n<<<DOCUMENT END>>>",
        response_model=PerDocExtractPayload,
    )
    result = await p.complete_structured(system="x", user="", response_model=SynthesisPayload)
    s = result.payload
    assert s.executive_summary
    assert len(s.assumptions) >= 1
    assert len(s.limitations) >= 1
