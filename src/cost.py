"""Token + cost tracking. Pure aggregation over LLMUsage records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.providers.base import LLMUsage


@dataclass
class StageCost:
    stage: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, usage: LLMUsage) -> None:
        self.calls += 1
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens


@dataclass
class CostTracker:
    """Per-stage usage accumulator with a per-1M-token price table."""

    prices: dict[str, dict[str, float]]
    model: str
    stages: dict[str, StageCost] = field(default_factory=dict)

    def add(self, stage: str, usage: LLMUsage) -> None:
        sc = self.stages.setdefault(stage, StageCost(stage=stage))
        sc.add(usage)

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self.stages.values())

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self.stages.values())

    @property
    def estimated_usd(self) -> float:
        prices = self.prices.get(self.model)
        if prices is None:
            return 0.0
        ip = prices.get("input_per_million", 0.0)
        op = prices.get("output_per_million", 0.0)
        return (self.total_input_tokens / 1_000_000) * ip + (self.total_output_tokens / 1_000_000) * op

    def summary(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": round(self.estimated_usd, 6),
            "by_stage": {
                name: {
                    "calls": s.calls,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                }
                for name, s in self.stages.items()
            },
        }
