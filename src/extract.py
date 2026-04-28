"""Map stage: per-document structured extraction.

One LLM call per document. The model returns a `PerDocExtractPayload` (no
source_file). We attach the filename ourselves so the model cannot hallucinate
which file it just read.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.prompts import MAP_SYSTEM, MAP_USER_TEMPLATE
from src.providers.base import LLMProvider, LLMResult
from src.schemas import PerDocExtract, PerDocExtractPayload

log = logging.getLogger(__name__)


async def extract_one(provider: LLMProvider, doc_path: Path) -> tuple[PerDocExtract, LLMResult[PerDocExtractPayload]]:
    """Extract structure from one document. Returns (PerDocExtract, raw LLM result)."""
    content = doc_path.read_text(encoding="utf-8", errors="replace")
    user = MAP_USER_TEMPLATE.format(filename=doc_path.name, content=content)
    result = await provider.complete_structured(
        system=MAP_SYSTEM,
        user=user,
        response_model=PerDocExtractPayload,
    )
    payload = result.payload
    extract = PerDocExtract(
        source_file=doc_path.name,
        themes=payload.themes,
        insights=payload.insights,
        risks=payload.risks,
        opportunities=payload.opportunities,
        actions=payload.actions,
        notes=payload.notes,
    )
    return extract, result
