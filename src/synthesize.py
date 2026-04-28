"""Synthesis stage: produce the executive narrative around the aggregated findings.

One LLM call. The model receives `AggregatedFindings` JSON and returns
`SynthesisPayload` (executive_summary + assumptions + limitations).
"""

from __future__ import annotations

import json
import logging

from src.prompts import SYNTHESIS_SYSTEM, SYNTHESIS_USER_TEMPLATE
from src.providers.base import LLMProvider, LLMResult
from src.schemas import AggregatedFindings, SynthesisPayload

log = logging.getLogger(__name__)


async def synthesise(
    provider: LLMProvider,
    findings: AggregatedFindings,
) -> tuple[SynthesisPayload, LLMResult[SynthesisPayload]]:
    """Render the executive narrative."""
    aggregate_json = json.dumps(findings.model_dump(), ensure_ascii=False, indent=None)
    user = SYNTHESIS_USER_TEMPLATE.format(aggregate_json=aggregate_json)
    result = await provider.complete_structured(
        system=SYNTHESIS_SYSTEM,
        user=user,
        response_model=SynthesisPayload,
    )
    return result.payload, result
