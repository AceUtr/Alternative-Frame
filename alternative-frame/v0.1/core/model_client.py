"""Configurable model client for v0.1.

The client uses the widely supported OpenAI-compatible chat API shape. It is
deliberately implemented with the standard library so v0.1 remains easy to run.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ModelConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout_seconds: int = 120

    @classmethod
    def from_env(cls) -> "ModelConfig":
        base_url = os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1")
        api_key = os.getenv("MODEL_API_KEY", "")
        model = os.getenv("MODEL_NAME", "")
        if not api_key or not model:
            raise ValueError("Set MODEL_API_KEY and MODEL_NAME before using an API model")
        return cls(
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=model,
            temperature=float(os.getenv("MODEL_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("MODEL_MAX_TOKENS", "4096")),
        )


class OpenAICompatibleClient:
    MAX_TRANSIENT_ATTEMPTS = 3
    RETRY_DELAYS_SECONDS = (0.5, 1.5)

    def __init__(self, config: ModelConfig):
        self.config = config

    def chat(self, messages: List[Dict[str, str]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            payload["tools"] = tools
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            endpoints = [base]
        elif base.endswith("/v1"):
            endpoints = [base + "/chat/completions"]
        else:
            # CCswitch deployments vary: some expose /v1, some expose the
            # OpenAI-compatible route directly. Try the conventional path first.
            endpoints = [base + "/v1/chat/completions", base + "/chat/completions"]

        errors = []
        data = None
        for request_url in endpoints:
            for attempt in range(1, self.MAX_TRANSIENT_ATTEMPTS + 1):
                request = urllib.request.Request(
                    request_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Accept": "application/json",
                    },
                    method="POST",
                )
                retry = False
                try:
                    with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            errors.append(
                                f"{request_url} attempt {attempt}: HTTP {response.status}, "
                                f"non-JSON body {raw[:120]!r}"
                            )
                            break
                except urllib.error.HTTPError as exc:
                    raw = exc.read().decode("utf-8", errors="replace")[:120]
                    errors.append(f"{request_url} attempt {attempt}: HTTP {exc.code}, body {raw!r}")
                    retry = exc.code == 429 or 500 <= exc.code < 600
                except (urllib.error.URLError, TimeoutError) as exc:
                    errors.append(f"{request_url} attempt {attempt}: {exc}")
                    retry = True

                if data is not None:
                    break
                if not retry or attempt >= self.MAX_TRANSIENT_ATTEMPTS:
                    break
                time.sleep(self.RETRY_DELAYS_SECONDS[attempt - 1])
            if data is not None:
                break

        if data is None:
            raise RuntimeError("CCswitch/API connection failed. Tried: " + " | ".join(errors))
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected model response: {data}") from exc
        return message
