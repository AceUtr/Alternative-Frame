import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.model_client import ModelConfig, OpenAICompatibleClient


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode("utf-8")


class UsageResponse(FakeResponse):
    def __init__(self, usage):
        self.usage = usage

    def read(self):
        return json.dumps({
            "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
            "usage": self.usage,
        }).encode("utf-8")


def test_transient_connection_errors_are_retried(monkeypatch):
    outcomes = [
        urllib.error.URLError("TLS handshake timed out"),
        urllib.error.URLError("TLS handshake timed out"),
        FakeResponse(),
    ]

    def fake_urlopen(_request, timeout):
        assert timeout == 120
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("core.model_client.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("core.model_client.time.sleep", lambda _delay: None)
    client = OpenAICompatibleClient(ModelConfig("https://example.test/v1", "secret", "model"))

    message = client.chat([{"role": "user", "content": "test"}])

    assert message["content"] == "OK"
    assert outcomes == []


def test_normalize_content_supports_reasoning_and_segmented_backends():
    assert OpenAICompatibleClient._normalize_content(
        {"content": "", "reasoning_content": '{"goal_summary":"ok"}'}
    ) == '{"goal_summary":"ok"}'
    assert OpenAICompatibleClient._normalize_content(
        {"content": [{"type": "text", "text": "part one"}, {"text": {"value": "part two"}}]}
    ) == "part one\npart two"
    assert OpenAICompatibleClient._normalize_content(
        {"content": None, "output_text": '{"goal_summary":"fallback field"}'}
    ) == '{"goal_summary":"fallback field"}'


def test_chat_can_limit_transport_attempts(monkeypatch):
    calls = []

    def always_timeout(_request, timeout):
        calls.append(timeout)
        raise TimeoutError("read operation timed out")

    monkeypatch.setattr("core.model_client.urllib.request.urlopen", always_timeout)
    client = OpenAICompatibleClient(ModelConfig("https://example.test/v1", "secret", "model"))

    try:
        client.chat([{"role": "user", "content": "test"}], max_attempts=1)
    except RuntimeError as exc:
        assert "timed out" in str(exc)
    else:
        raise AssertionError("timeout must be surfaced")
    assert calls == [120]


def test_dns_failure_is_reported_as_hostname_resolution_problem(monkeypatch):
    monkeypatch.setattr(
        "core.model_client.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            urllib.error.URLError("[Errno 11001] getaddrinfo failed")
        ),
    )
    monkeypatch.setattr("core.model_client.time.sleep", lambda _delay: None)
    client = OpenAICompatibleClient(ModelConfig("https://example.test/v1", "secret", "model"))

    try:
        client.chat([{"role": "user", "content": "test"}], max_attempts=1)
    except RuntimeError as exc:
        assert "域名无法解析" in str(exc)
        assert "尚未到达服务端" in str(exc)
        assert "getaddrinfo failed" in str(exc)
        assert "CCswitch" not in str(exc)
    else:
        raise AssertionError("DNS failure must be surfaced")


def test_http_failure_is_not_mislabeled_as_dns_failure():
    message = OpenAICompatibleClient._format_request_error(["https://example.test/v1 attempt 1: HTTP 401, body 'unauthorized'"])

    assert "HTTP 错误" in message
    assert "域名无法解析" not in message


def test_global_budget_accounts_provider_usage_and_blocks_next_call(monkeypatch):
    config = ModelConfig(
        "https://example.test/v1", "secret", "model", max_tokens=64,
        global_token_limit=80, max_model_calls=5, max_runtime_seconds=60,
    )
    calls = []

    def respond(request, timeout):
        calls.append(json.loads(request.data.decode("utf-8"))["max_tokens"])
        return UsageResponse({"prompt_tokens": 20, "completion_tokens": 50, "total_tokens": 70})

    monkeypatch.setattr("core.model_client.urllib.request.urlopen", respond)
    client = OpenAICompatibleClient(config)
    response = client.chat([{"role": "user", "content": "first call"}])

    assert response["_usage"]["total_tokens"] == 70
    assert client.budget_snapshot()["total_tokens"] == 70
    try:
        client.chat([{"role": "user", "content": "second call"}])
    except RuntimeError as exc:
        assert "global token budget exhausted" in str(exc)
    else:
        raise AssertionError("the global budget must stop a call before it is sent")
    assert len(calls) == 1


def test_missing_provider_usage_is_marked_as_estimated(monkeypatch):
    monkeypatch.setattr("core.model_client.urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())
    client = OpenAICompatibleClient(ModelConfig("https://example.test/v1", "secret", "model"))

    client.chat([{"role": "user", "content": "test"}])

    snapshot = client.budget_snapshot()
    assert snapshot["total_tokens"] > 0
    assert snapshot["estimated_usage_calls"] == 1


def test_resumed_client_keeps_the_previous_run_budget(monkeypatch):
    config = ModelConfig(
        "https://example.test/v1", "secret", "model", max_tokens=32,
        global_token_limit=80, max_model_calls=5, max_runtime_seconds=60,
    )
    monkeypatch.setattr(
        "core.model_client.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("request must be blocked")),
    )
    client = OpenAICompatibleClient(
        config,
        initial_usage={"requests": 1, "total_tokens": 70, "estimated_usage_calls": 0, "elapsed_seconds": 1},
    )

    try:
        client.chat([{"role": "user", "content": "resume"}])
    except RuntimeError as exc:
        assert "global token budget exhausted" in str(exc)
    else:
        raise AssertionError("resuming must retain the prior run's token usage")
