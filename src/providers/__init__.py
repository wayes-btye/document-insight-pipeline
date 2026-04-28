"""LLM provider abstraction.

Two implementations:
- `MockProvider`: deterministic, keyword-driven, no API key required. First-class citizen.
- `OpenRouterProvider`: OpenAI SDK pointed at OpenRouter. Default for real runs.
"""

from src.providers.base import LLMProvider, LLMUsage
from src.providers.mock import MockProvider
from src.providers.openrouter import OpenRouterProvider

__all__ = ["LLMProvider", "LLMUsage", "MockProvider", "OpenRouterProvider"]
