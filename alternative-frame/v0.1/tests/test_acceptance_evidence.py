import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.acceptance import AcceptanceEvaluator
from core.models import AgentResult, SubTask


def command_task():
    return SubTask(
        "tests",
        "tester",
        "run exact tests",
        metadata={
            "checks": [
                {
                    "id": "tests_pass",
                    "check_type": "command",
                    "command": "python -m unittest -v",
                }
            ]
        },
    )


def test_command_acceptance_rejects_a_different_successful_command(tmp_path):
    result = AgentResult(
        "tests",
        "success",
        tool_records=[
            {
                "tool": "test_runner",
                "arguments": {"command": "pytest -q"},
                "success": True,
                "exit_code": 0,
            }
        ],
    )

    report = AcceptanceEvaluator(tmp_path).evaluate(command_task(), result)

    assert report.passed is False
    assert "exact_command_evidence_missing" in report.failures[0]


def test_command_acceptance_requires_exit_code_zero(tmp_path):
    result = AgentResult(
        "tests",
        "success",
        tool_records=[
            {
                "tool": "test_runner",
                "arguments": {"command": "python -m unittest -v"},
                "success": False,
                "exit_code": 1,
            }
        ],
    )

    report = AcceptanceEvaluator(tmp_path).evaluate(command_task(), result)

    assert report.passed is False


def test_command_acceptance_passes_with_exact_exit_code_zero_record(tmp_path):
    result = AgentResult(
        "tests",
        "success",
        tool_records=[
            {
                "tool": "test_runner",
                "arguments": {"command": "  python   -m unittest -v  "},
                "success": True,
                "exit_code": 0,
            }
        ],
    )

    report = AcceptanceEvaluator(tmp_path).evaluate(command_task(), result)

    assert report.passed is True
