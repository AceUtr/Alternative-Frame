"""Configurable model client for v0.1.

The client uses the widely supported OpenAI-compatible chat API shape. It is
deliberately implemented with the standard library so v0.1 remains easy to run.
"""

from __future__ import annotations

import json
import math
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
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
    global_token_limit: int = 64000
    max_model_calls: int = 30
    max_runtime_seconds: int = 600
    long_horizon_max_phases: int = 12
    long_horizon_max_tasks: int = 200

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
            global_token_limit=int(os.getenv("MODEL_GLOBAL_TOKEN_LIMIT", "64000")),
            max_model_calls=int(os.getenv("MODEL_MAX_CALLS", "30")),
            max_runtime_seconds=int(os.getenv("MODEL_MAX_RUNTIME_SECONDS", "600")),
        )


class ModelCallBudget:
    """Per-client limits shared by all concurrent calls in one UI run."""

    def __init__(self, config: ModelConfig, initial_usage: Dict[str, Any] | None = None):
        if min(config.max_tokens, config.global_token_limit, config.max_model_calls, config.max_runtime_seconds) < 1:
            raise ValueError("model call and run budgets must be positive")
        self.config = config
        self._lock = threading.Lock()
        self._update_lock = threading.Lock()
        self._started_at = None
        initial_usage = initial_usage or {}
        self._calls = int(initial_usage.get("requests", 0))
        # A request that was in flight at the last checkpoint may have been
        # billed even if the process died before receiving its response.
        self._tokens = int(initial_usage.get("total_tokens", 0))
        self._unconfirmed_tokens = int(initial_usage.get("unconfirmed_reserved_tokens", 0)) + int(initial_usage.get("in_flight_reserved_tokens", 0))
        self._estimated_calls = int(initial_usage.get("estimated_usage_calls", 0))
        self._provider_calls = int(initial_usage.get("provider_usage_calls", max(0, self._calls - self._estimated_calls)))
        self._transport_attempts = int(initial_usage.get("transport_attempts", self._calls))
        self._prior_elapsed = float(initial_usage.get("elapsed_seconds", 0.0))
        self._pending: dict[str, int] = {}

    @staticmethod
    def estimate_tokens(value: Any) -> int:
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        return max(1, math.ceil(len(serialized) / 4))

    def reserve(self, prompt_tokens: int) -> tuple[str, int]:
        with self._lock:
            now = time.monotonic()
            if self._started_at is None:
                self._started_at = now
            if self._prior_elapsed + now - self._started_at >= self.config.max_runtime_seconds:
                raise RuntimeError("global run time budget exhausted")
            if self._calls >= self.config.max_model_calls:
                raise RuntimeError("global model call budget exhausted")
            reserved = sum(self._pending.values())
            remaining = self.config.global_token_limit - self._tokens - self._unconfirmed_tokens - reserved
            output_limit = min(self.config.max_tokens, remaining - prompt_tokens)
            if output_limit < 1:
                raise RuntimeError("global token budget exhausted before the next model call")
            call_id = str(self._calls + 1)
            self._pending[call_id] = prompt_tokens + output_limit
            self._calls += 1
            return call_id, output_limit

    def settle(self, call_id: str, actual_tokens: int, estimated: bool = False):
        with self._lock:
            if self._pending.pop(call_id, None) is None:
                raise ValueError("unknown or already settled model call")
            if estimated:
                self._estimated_calls += 1
            else:
                self._provider_calls += 1
            self._tokens += actual_tokens
            if self._tokens > self.config.global_token_limit:
                raise RuntimeError("provider usage exceeded the global token budget after the call completed")

    def cancel(self, call_id: str):
        with self._lock:
            self._pending.pop(call_id, None)

    def mark_uncertain(self, call_id: str):
        with self._lock:
            self._unconfirmed_tokens += self._pending.get(call_id, 0)

    def snapshot(self) -> dict[str, int | float | str | None]:
        with self._lock:
            elapsed = self._prior_elapsed + (0.0 if self._started_at is None else time.monotonic() - self._started_at)
            return {
                "requests": self._calls,
                "total_tokens": self._tokens,
                "remaining_tokens": max(0, self.config.global_token_limit - self._tokens - self._unconfirmed_tokens),
                "unconfirmed_reserved_tokens": self._unconfirmed_tokens,
                "in_flight_reserved_tokens": sum(self._pending.values()),
                "estimated_usage_calls": self._estimated_calls,
                "provider_usage_calls": self._provider_calls,
                "transport_attempts": self._transport_attempts,
                "elapsed_seconds": round(elapsed, 1),
                "global_token_limit": self.config.global_token_limit,
                "max_model_calls": self.config.max_model_calls,
                "max_runtime_seconds": self.config.max_runtime_seconds,
            }

    def remaining_runtime_seconds(self) -> float:
        return max(0.0, self.config.max_runtime_seconds - float(self.snapshot()["elapsed_seconds"]))


class OpenAICompatibleClient:
    MAX_TRANSIENT_ATTEMPTS = 6
    RETRY_DELAYS_SECONDS = (1, 2, 4, 8, 16)
    MAX_RETRY_AFTER_SECONDS = 300

    def __init__(self, config: ModelConfig, initial_usage: Dict[str, Any] | None = None, on_budget_update=None, on_request_event=None):
        self.config = config
        self.budget = ModelCallBudget(config, initial_usage)
        self.on_budget_update = on_budget_update
        self.on_request_event = on_request_event
        self._cooldown_until = 0.0
        self._cooldown_lock = threading.Lock()

    def _emit_request(self, event, payload):
        if self.on_request_event:
            try:
                self.on_request_event(event, payload)
            except Exception as exc:
                raise RuntimeError(f"API event checkpoint failed: {type(exc).__name__}") from exc

    def _safe_error_body(self, value: str) -> str:
        if self.config.api_key:
            value = value.replace(self.config.api_key, "<redacted>")
        return re.sub(r"sk-[A-Za-z0-9_-]{16,}", "<redacted>", value)

    def _notify_budget_update(self):
        if self.on_budget_update:
            with self.budget._update_lock:
                try:
                    self.on_budget_update(self.budget.snapshot())
                except Exception as exc:
                    raise RuntimeError(f"API usage checkpoint failed: {type(exc).__name__}") from exc

    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_attempts: Optional[int] = None,
    ) -> Dict[str, Any]:
        transient_attempts = self.MAX_TRANSIENT_ATTEMPTS if max_attempts is None else max_attempts
        if transient_attempts < 1:
            raise ValueError("max_attempts must be positive")
        prompt_tokens = self.budget.estimate_tokens({"messages": messages, "tools": tools or []})
        call_id, output_limit = self.budget.reserve(prompt_tokens)
        try:
            self._notify_budget_update()
            return self._chat_reserved(messages, tools, transient_attempts, prompt_tokens, call_id, output_limit)
        finally:
            # Every exception path releases its own reservation, including
            # invalid endpoints, interrupted reads and checkpoint failures.
            self.budget.cancel(call_id)
            self._notify_budget_update()

    def _chat_reserved(self, messages, tools, transient_attempts, prompt_tokens, call_id, output_limit):
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": output_limit,
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
            for attempt in range(1, transient_attempts + 1):
                remaining = self.budget.remaining_runtime_seconds()
                with self._cooldown_lock:
                    wait = max(0.0, self._cooldown_until - time.monotonic())
                if wait:
                    if remaining <= wait:
                        errors.append("global run time budget exhausted before provider cooldown ends")
                        break
                    time.sleep(wait)
                remaining = self.budget.remaining_runtime_seconds()
                if remaining <= 0:
                    errors.append("global run time budget exhausted")
                    break
                with self.budget._lock:
                    if self.budget._tokens + self.budget._unconfirmed_tokens + sum(self.budget._pending.values()) > self.config.global_token_limit:
                        errors.append("global token budget exhausted by unconfirmed transport usage")
                        break
                    if self.budget._transport_attempts >= self.config.max_model_calls:
                        errors.append("global model call budget exhausted before transport attempt")
                        break
                    self.budget._transport_attempts += 1
                self._notify_budget_update()
                self._emit_request("api_request_started", {"attempt": attempt})
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
                retry_delay = self.RETRY_DELAYS_SECONDS[min(attempt - 1, len(self.RETRY_DELAYS_SECONDS) - 1)]
                try:
                    with urllib.request.urlopen(request, timeout=min(self.config.timeout_seconds, max(0.001, remaining))) as response:
                        raw = response.read().decode("utf-8", errors="replace")
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            errors.append(
                                f"{request_url} attempt {attempt}: HTTP {response.status}, "
                                f"non-JSON body {self._safe_error_body(raw[:120])!r}"
                            )
                            break
                except urllib.error.HTTPError as exc:
                    raw = exc.read().decode("utf-8", errors="replace")[:4096]
                    safe_raw = raw.replace(self.config.api_key, "<redacted>") if self.config.api_key else raw
                    errors.append(f"attempt {attempt}: HTTP {exc.code}, body {self._safe_error_body(safe_raw[:300])!r}")
                    retry = exc.code == 429 or 500 <= exc.code < 600
                    retry_delay = self._retry_delay(exc.headers, raw, retry_delay)
                except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
                    self.budget.mark_uncertain(call_id)
                    self._notify_budget_update()
                    errors.append(f"attempt {attempt}: {type(exc).__name__}: {self._safe_error_body(str(exc))}")
                    retry = True

                if data is not None:
                    break
                if not retry or attempt >= transient_attempts:
                    break
                if retry_delay > self.MAX_RETRY_AFTER_SECONDS:
                    errors.append("provider cooldown exceeds automatic waiting window; resume later")
                    break
                if self.budget.remaining_runtime_seconds() <= retry_delay:
                    errors.append("retry stopped because the configured run-time budget cannot cover the provider cooldown")
                    break
                self._emit_request("api_retry_wait", {"attempt": attempt, "wait_seconds": retry_delay})
                with self._cooldown_lock:
                    self._cooldown_until = max(self._cooldown_until, time.monotonic() + retry_delay)
            if data is not None:
                break

        if data is None:
            self.budget.cancel(call_id)
            self._notify_budget_update()
            raise RuntimeError(self._format_request_error(errors))
        try:
            choice = data["choices"][0]
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError(f"unexpected model message: {message!r}")
            message = dict(message)
            message["content"] = self._normalize_content(message)
        except (KeyError, IndexError, TypeError) as exc:
            self.budget.cancel(call_id)
            self._notify_budget_update()
            raise RuntimeError("unexpected model response: missing valid choices/message") from exc
        usage = data.get("usage") if isinstance(data, dict) else None
        provider_usage_valid = False
        if isinstance(usage, dict):
            prompt_usage = usage.get("prompt_tokens", usage.get("input_tokens"))
            completion_usage = usage.get("completion_tokens", usage.get("output_tokens"))
            total_usage = usage.get("total_tokens")
            try:
                actual_tokens = int(total_usage) if total_usage is not None else int(prompt_usage or 0) + int(completion_usage or 0)
                provider_usage_valid = actual_tokens >= 0 and (total_usage is not None or prompt_usage is not None or completion_usage is not None)
                if not provider_usage_valid:
                    actual_tokens = None
            except (TypeError, ValueError):
                actual_tokens = None
            message["_usage"] = usage
        else:
            actual_tokens = None
        if actual_tokens is None:
            # Use the observed response length when provider accounting is absent.
            actual_tokens = prompt_tokens + self.budget.estimate_tokens(message)
        try:
            self.budget.settle(call_id, actual_tokens, estimated=not provider_usage_valid)
        finally:
            self._notify_budget_update()
        self._emit_request("api_request_finished", {"usage_source": "provider" if provider_usage_valid else "estimated"})
        message["_finish_reason"] = choice.get("finish_reason")
        return message

    def budget_snapshot(self):
        return self.budget.snapshot()

    @classmethod
    def _retry_delay(cls, headers, body: str, fallback: float) -> float:
        value = headers.get("Retry-After") if headers else None
        if value:
            try:
                seconds = float(value)
                return max(0.0, seconds) if math.isfinite(seconds) else fallback
            except ValueError:
                try:
                    when = parsedate_to_datetime(value)
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    pass
        match = re.search(r"cooldown\s+wait\s+(\d+(?:\.\d+)?)\s*s?", body, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return fallback

    @staticmethod
    def _format_request_error(errors: List[str]) -> str:
        details = " | ".join(errors) or "未收到服务端响应"
        lowered = details.lower()
        if "getaddrinfo failed" in lowered or "name or service not known" in lowered or "no such host" in lowered:
            summary = "模型 API 域名无法解析。请检查 Base URL、DNS 或当前网络；请求尚未到达服务端。"
        elif "timed out" in lowered or "timeout" in lowered:
            summary = "连接模型 API 超时。请检查网络、服务状态或稍后重试。"
        elif "connection refused" in lowered or "actively refused" in lowered:
            summary = "模型 API 拒绝了连接。请检查服务地址、端口及服务状态。"
        elif "http " in lowered:
            summary = "模型 API 已返回 HTTP 错误。请根据状态码检查认证、模型名、请求额度或服务状态。"
        else:
            summary = "无法完成模型 API 请求。请检查 Base URL、网络和服务配置。"
        return f"{summary}\n诊断信息：{details}"

    @staticmethod
    def _normalize_content(message: Dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, dict) and isinstance(text.get("value"), str):
                    parts.append(text["value"])
            if parts:
                return "\n".join(parts)
        # Several OpenAI-compatible reasoning backends expose the final JSON
        # here while leaving content null/empty.
        for field in ("reasoning_content", "reasoning", "analysis", "text", "output_text"):
            value = message.get(field)
            if isinstance(value, str) and value.strip():
                return value
        return ""
