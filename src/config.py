"""Config loader. config.yaml is the source of truth for defaults; CLI flags override."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ProviderConfig:
    model: str = "openai/gpt-4o-mini"
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 60.0


@dataclass
class PipelineConfig:
    concurrency: int = 5
    max_retries: int = 3
    output_basename: str = "summary_report"
    format: str = "both"  # "md", "json", or "both"


@dataclass
class CacheConfig:
    enabled: bool = False
    directory: str = ".cache"


@dataclass
class CostConfig:
    prices: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class Config:
    provider: ProviderConfig
    pipeline: PipelineConfig
    cache: CacheConfig
    cost: CostConfig

    @classmethod
    def from_file(cls, path: Path | str) -> Config:
        path = Path(path)
        with path.open() as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return cls(
            provider=ProviderConfig(**(raw.get("provider") or {})),
            pipeline=PipelineConfig(**(raw.get("pipeline") or {})),
            cache=CacheConfig(**(raw.get("cache") or {})),
            cost=CostConfig(**(raw.get("cost") or {})),
        )

    @classmethod
    def defaults(cls) -> Config:
        return cls(
            provider=ProviderConfig(),
            pipeline=PipelineConfig(),
            cache=CacheConfig(),
            cost=CostConfig(),
        )
