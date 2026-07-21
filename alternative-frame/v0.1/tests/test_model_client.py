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
