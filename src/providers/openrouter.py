"""OpenRouter provider via the OpenAI Python SDK.

OpenRouter is OpenAI-API-compatible: same client, different `base_url`. We use
the SDK's `chat.completions.parse()` helper which converts a Pydantic model to
JSON schema, sends it as `response_format`, and parses the response back into
the model. Built-in SDK retries handle transient 429/5xx; tenacity layers an
extra retry on schema-validation failures.
"""

from __future__ import annotations

import logging
import os
from typing import TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.providers.base import LLMProvider, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        *,
        model: str = "openai/gpt-4o-mini",
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 60.0,
        sdk_max_retries: int = 2,
        max_validation_retries: int = 2,
    ) -> None:
        self.model = model
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY not set. Either pass --mock to use the deterministic provider, "
                "or set the environment variable (e.g. via .env)."
            )
        self._client = AsyncOpenAI(
            api_key=key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=sdk_max_retries,
            default_headers={
                # OpenRouter recommends these for their dashboard. Optional.
                "HTTP-Referer": "https://github.com/wayes-btye/document-insight-pipeline",
                "X-Title": "document-insight-pipeline",
            },
        )
        self._max_validation_retries = max_validation_retries

    async def complete_structured(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> LLMResult[T]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_validation_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type((ValueError, APIError)),
            reraise=True,
        ):
            with attempt:
                completion = await self._client.chat.completions.parse(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format=response_model,
                )
                msg = completion.choices[0].message
                if msg.refusal:
                    raise ValueError(f"model refused: {msg.refusal}")
                if msg.parsed is None:
                    raise ValueError("model returned no parsed payload")
                usage = completion.usage
                if usage is None:
                    in_tokens, out_tokens = 0, 0
                else:
                    in_tokens, out_tokens = usage.prompt_tokens, usage.completion_tokens
                return LLMResult(
                    payload=msg.parsed,
                    usage=LLMUsage(input_tokens=in_tokens, output_tokens=out_tokens),
                )
        raise RuntimeError("unreachable: AsyncRetrying always raises or returns")


_ = LLMProvider  # protocol satisfaction
