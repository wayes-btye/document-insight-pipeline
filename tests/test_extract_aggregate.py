"""Tests for the map and reduce stage wrappers (provider-agnostic)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.aggregate import aggregate
from src.extract import extract_one
from src.providers.mock import MockProvider
from src.schemas import PerDocExtract


@pytest.mark.asyncio
async def test_extract_pins_source_file(tmp_path: Path):
    provider = MockProvider()
    p = tmp_path / "doc.txt"
    p.write_text("renewal pricing discussion")
    extract, result = await extract_one(provider, p)
    assert extract.source_file == "doc.txt"
    assert result.usage.input_tokens > 0


@pytest.mark.asyncio
async def test_aggregate_returns_findings_with_citations():
    provider = MockProvider()
    extracts = [
        PerDocExtract(source_file="a.txt", themes=["Pricing pressure on renewals"],
                      insights=[], risks=[], opportunities=[], actions=[], notes=None),
        PerDocExtract(source_file="b.txt", themes=["Pricing pressure on renewals"],
                      insights=[], risks=[], opportunities=[], actions=[], notes=None),
    ]
    # Mock keeps internal state from prior extracts; aggregate uses _that_ state, so seed it directly.
    provider._extracts = [(e.source_file, e) for e in extracts]  # type: ignore[attr-defined]

    findings, _result = await aggregate(provider, extracts)
    assert any("Pricing" in t.name for t in findings.themes)
    pricing = next(t for t in findings.themes if "Pricing" in t.name)
    assert set(pricing.citations) == {"a.txt", "b.txt"}
