"""LLM provider interface.

A provider takes (system, user, response_model) and returns a parsed Pydantic
instance plus token-usage telemetry. The pipeline never sees provider-specific
types beyond what's defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMUsage:
    """Token counts for one LLM call. Aggregated across calls by `cost.py`."""

    input_tokens: int
    output_tokens: int


@dataclass
class LLMResult(Generic[T]):
    """Parsed payload + usage telemetry from one provider call."""

    payload: T
    usage: LLMUsage


class LLMProvider(Protocol):
    """The full provider interface. Both Mock and OpenRouter implement this."""

    name: str
    model: str

    async def complete_structured(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> LLMResult[T]:
        """Make one structured LLM call and return the parsed payload + usage."""
        ...
