import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.models import AgentResult
from core.retry import RetryFailureClassifier


def test_global_budget_exhaustion_is_not_retried():
    result = AgentResult(
        "implementation",
        "failed",
        failures=["agent_exception: RuntimeError: global token budget exhausted before the next model call"],
    )

    assert RetryFailureClassifier().retryable(result) is False


def test_provider_timeout_is_not_retried_to_avoid_duplicate_billed_generation():
    result = AgentResult(
        "implementation",
        "failed",
        failures=["agent_exception: RuntimeError: 连接模型 API 超时。The read operation timed out"],
    )

    assert RetryFailureClassifier().retryable(result) is False
