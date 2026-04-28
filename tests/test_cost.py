"""Tests for the cost tracker math."""

from __future__ import annotations

from src.cost import CostTracker
from src.providers.base import LLMUsage


def test_cost_tracker_aggregates_per_stage():
    ct = CostTracker(
        prices={"openai/gpt-4o-mini": {"input_per_million": 0.15, "output_per_million": 0.60}},
        model="openai/gpt-4o-mini",
    )
    ct.add("map", LLMUsage(input_tokens=1_000_000, output_tokens=500_000))
    ct.add("map", LLMUsage(input_tokens=500_000, output_tokens=250_000))
    ct.add("reduce", LLMUsage(input_tokens=200_000, output_tokens=100_000))

    assert ct.total_input_tokens == 1_700_000
    assert ct.total_output_tokens == 850_000
    # 1.7M input * 0.15 + 0.85M output * 0.60 = 0.255 + 0.51 = 0.765
    assert round(ct.estimated_usd, 6) == 0.765

    summary = ct.summary()
    assert summary["by_stage"]["map"]["calls"] == 2
    assert summary["by_stage"]["reduce"]["calls"] == 1


def test_cost_tracker_returns_zero_for_unknown_model():
    ct = CostTracker(prices={}, model="some/unknown-model")
    ct.add("map", LLMUsage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert ct.estimated_usd == 0.0
