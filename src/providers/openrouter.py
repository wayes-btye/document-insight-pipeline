"""OpenRouter provider via the OpenAI Python SDK.

OpenRouter is OpenAI-API-compatible: same client, different `base_url`. But the
OpenAI SDK's `chat.completions.parse()` helper wraps Pydantic validation inside
the SDK call — by the time it raises ValidationError, the raw response content
is gone. That's a problem for non-OpenAI models routed via OpenRouter, which
often return text refusals or JSON-in-markdown wrappers that need our own
parsing logic to handle gracefully.

So: for OpenAI-prefixed models we use `parse()` (strict schema enforcement at
the API). For everything else we use `create()` with `response_format=
{"type": "json_object"}` and parse the content ourselves. Both paths retry on
transient errors.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.providers.base import LLMProvider, LLMResult, LLMUsage

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json|javascript)?\s*\n?", re.IGNORECASE)


def _strip_json_fences(content: str) -> str:
    """Remove ```json ... ``` wrappers some models add around JSON output."""
    s = content.strip()
    s = _FENCE_RE.sub("", s, count=1)
    if s.rstrip().endswith("```"):
        s = s.rstrip()[:-3].rstrip()
    return s.strip()


class ProviderRefusal(ValueError):
    """The model returned a refusal field. Don't retry — same prompt will refuse again."""


class NonJSONContent(ValueError):
    """The model returned content that isn't JSON (likely a text refusal)."""


def _supports_native_structured(model: str) -> bool:
    """Whether the model supports OpenAI's strict structured-output protocol.

    Currently: OpenAI models on OpenRouter do. Most others (Anthropic, Google,
    Meta, Mistral) get JSON mode + manual parsing instead. This is a heuristic
    based on observed behaviour, not a contract. Easy to tune via this list.
    """
    return model.startswith("openai/") or model.startswith("openrouter/")


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        *,
        model: str = "openai/gpt-4o-mini",
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 60.0,
        temperature: float = 0.0,
        sdk_max_retries: int = 2,
        max_validation_retries: int = 2,
    ) -> None:
        self.model = model
        self._temperature = temperature
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
            retry=retry_if_exception_type((NonJSONContent, ValidationError, APIError)),
            reraise=True,
        ):
            with attempt:
                if _supports_native_structured(self.model):
                    return await self._call_native(system=system, user=user, response_model=response_model)
                return await self._call_json_mode(system=system, user=user, response_model=response_model)
        raise RuntimeError("unreachable: AsyncRetrying always raises or returns")

    async def _call_native(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> LLMResult[T]:
        """OpenAI-strict path: SDK enforces schema at the API."""
        completion = await self._client.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=response_model,
            temperature=self._temperature,
        )
        msg = completion.choices[0].message
        if msg.refusal:
            raise ProviderRefusal(f"model refused: {msg.refusal}")
        if msg.parsed is None:
            raise NonJSONContent(f"model {self.model} returned no parsed payload")
        return LLMResult(payload=msg.parsed, usage=_usage(completion))

    async def _call_json_mode(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> LLMResult[T]:
        """Universal path: ask for JSON mode, parse + validate ourselves.

        Inject the JSON schema into the system prompt so the model knows the shape.
        Use `response_format={"type": "json_object"}` which is supported broadly across
        providers. Pydantic catches anything that doesn't conform.
        """
        schema = response_model.model_json_schema()
        system_with_schema = (
            f"{system}\n\n"
            f"Return your response as a single JSON object that conforms exactly to this schema. "
            f"No surrounding prose, no markdown fences, no explanation. Schema:\n"
            f"```json\n{json.dumps(schema, indent=2)}\n```"
        )
        completion = await self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature,
        )
        content = completion.choices[0].message.content or ""
        cleaned = _strip_json_fences(content)
        if not cleaned:
            raise NonJSONContent(f"model {self.model} returned empty content")
        try:
            parsed_dict = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            snippet = cleaned[:200].replace("\n", " ")
            raise NonJSONContent(
                f"model {self.model} returned non-JSON content (first 200 chars): {snippet!r}"
            ) from exc
        payload = response_model.model_validate(parsed_dict)
        log.debug("json-mode parse succeeded for model=%s", self.model)
        return LLMResult(payload=payload, usage=_usage(completion))


def _usage(completion) -> LLMUsage:  # type: ignore[no-untyped-def]
    usage = completion.usage
    if usage is None:
        return LLMUsage(input_tokens=0, output_tokens=0)
    return LLMUsage(input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens)


_ = LLMProvider  # protocol satisfaction
