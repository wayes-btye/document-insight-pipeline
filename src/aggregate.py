"""Reduce stage: aggregate PerDocExtracts into AggregatedFindings.

One LLM call. The model receives a JSON dump of all per-doc extracts and returns
clustered themes, insights, risks, opportunities and actions with citations.

Operates over compact structured extracts, not raw text. This keeps the reduce
prompt small even for large corpora.
"""

from __future__ import annotations

import json
import logging

from src.prompts import REDUCE_SYSTEM, REDUCE_USER_TEMPLATE
from src.providers.base import LLMProvider, LLMResult
from src.schemas import AggregatedFindings, PerDocExtract

log = logging.getLogger(__name__)


async def aggregate(
    provider: LLMProvider,
    extracts: list[PerDocExtract],
) -> tuple[AggregatedFindings, LLMResult[AggregatedFindings]]:
    """Aggregate per-document extracts into portfolio-level findings."""
    extracts_json = json.dumps(
        [e.model_dump() for e in extracts],
        ensure_ascii=False,
        indent=None,
    )
    user = REDUCE_USER_TEMPLATE.format(n_docs=len(extracts), extracts_json=extracts_json)
    result = await provider.complete_structured(
        system=REDUCE_SYSTEM,
        user=user,
        response_model=AggregatedFindings,
    )
    return result.payload, result
