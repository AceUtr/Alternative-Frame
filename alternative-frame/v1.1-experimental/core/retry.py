from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import List

from .models import AgentResult, SubTask


@dataclass
class RetryFeedback:
    attempt: int
    category: str
    failures: List[str]
    previous_summary: str
    successful_artifacts: List[str]
    directives: List[str]

    def to_dict(self):
        return asdict(self)


class RetryFailureClassifier:
    """Classify task failures and produce concrete correction instructions."""

    TERMINAL_CODES = {"max_tool_steps_exceeded", "repeated_tool_call"}
    NON_RETRYABLE_MARKERS = (
        "permission denied",
        "unauthorized",
        "http 401",
        "http 403",
        "unknown role",
        "cannot use tools",
    )

    def retryable(self, result: AgentResult) -> bool:
        lowered = " ".join(result.failures).lower()
        if any(code in result.failures for code in self.TERMINAL_CODES):
            return False
        return not any(marker in lowered for marker in self.NON_RETRYABLE_MARKERS)

    def build_feedback(self, task: SubTask, result: AgentResult, attempt: int) -> RetryFeedback:
        failures = list(dict.fromkeys(result.failures))
        lowered = " ".join(failures).lower()
        if "missing_artifacts" in lowered or "run_provenance" in lowered:
            category = "missing_artifact"
            directives = [
                "Use file_editor to create or update every missing expected output at the exact relative path.",
                "Do not finish with prose only; verify the files exist and preserve tool evidence.",
            ]
        elif "exact_command" in lowered or "exit_code" in lowered:
            category = "command_verification"
            directives = [
                "Run the exact command declared by the acceptance check with test_runner or shell_runner.",
                "If it fails, inspect the output, repair the implementation, and rerun until exit_code is 0.",
            ]
        elif "metric_evidence" in lowered:
            category = "metric_evidence"
            directives = ["Run the required experiment and report the named metric with structured evidence."]
        elif "evidence_missing" in lowered:
            category = "evidence_missing"
            directives = ["Provide concrete verification evidence tied to each acceptance check."]
        else:
            category = "execution_failure"
            directives = ["Change the previous approach and directly resolve every listed failure before stopping."]
        return RetryFeedback(
            attempt=attempt,
            category=category,
            failures=failures,
            previous_summary=(result.summary or "")[:1000],
            successful_artifacts=list(dict.fromkeys(result.artifacts)),
            directives=directives,
        )
