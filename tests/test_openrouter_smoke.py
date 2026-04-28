"""Smoke test against the real OpenRouter API.

Marked @pytest.mark.expensive — skipped by default. Run with:
    pytest -m expensive
or
    make test-all
"""

from __future__ import annotations

import os

import pytest

from src.providers.openrouter import OpenRouterProvider
from src.schemas import PerDocExtractPayload


@pytest.mark.expensive
@pytest.mark.asyncio
async def test_openrouter_returns_schema_valid_extract():
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    provider = OpenRouterProvider(model="openai/gpt-4o-mini")
    user = (
        "SOURCE_FILE: smoke.txt\n"
        "<<<DOCUMENT START>>>\n"
        "Karen at Lattice raised renewal pricing pressure during the QBR. Apex was named as a competing quote.\n"
        "Karen also asked about a Salesforce connector.\n"
        "<<<DOCUMENT END>>>"
    )
    result = await provider.complete_structured(
        system="Extract themes and risks from the document. Be selective.",
        user=user,
        response_model=PerDocExtractPayload,
    )
    payload = result.payload
    # Schema validation already happened inside the provider; sanity check shape.
    assert isinstance(payload.themes, list)
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0
