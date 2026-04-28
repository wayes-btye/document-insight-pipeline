"""Content-hash cache for LLM responses. Disabled by default in production.

Keyed on sha256(model + system + user + response_model_name). On a cache hit,
returns the parsed payload + zero-token usage. On a miss, the caller proceeds
normally and stores the result via `put`.

For dev iteration on the reduce/synthesis prompts you don't want to re-bill the
per-doc map stage. Enable via config.yaml or `--cache`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _key(model: str, system: str, user: str, response_model_name: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\x00")
    h.update(system.encode())
    h.update(b"\x00")
    h.update(user.encode())
    h.update(b"\x00")
    h.update(response_model_name.encode())
    return h.hexdigest()


class ResponseCache:
    def __init__(self, directory: Path, *, enabled: bool) -> None:
        self.directory = directory
        self.enabled = enabled
        if self.enabled:
            self.directory.mkdir(parents=True, exist_ok=True)

    def get(self, *, model: str, system: str, user: str, response_model_name: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        path = self.directory / f"{_key(model, system, user, response_model_name)}.json"
        if not path.exists():
            return None
        with path.open() as f:
            data: dict[str, Any] = json.load(f)
        return data

    def put(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model_name: str,
        payload: dict[str, Any],
    ) -> None:
        if not self.enabled:
            return
        path = self.directory / f"{_key(model, system, user, response_model_name)}.json"
        with path.open("w") as f:
            json.dump(payload, f)
