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


def file_task():
    return SubTask(
        "requirements",
        "analyst",
        "write requirements",
        metadata={
            "expected_outputs": ["requirements.md"],
            "checks": [{"id": "requirements_written", "check_type": "file_exists"}],
        },
    )


def test_file_acceptance_rejects_a_stale_file_without_run_provenance(tmp_path):
    (tmp_path / "requirements.md").write_text("stale", encoding="utf-8")

    report = AcceptanceEvaluator(tmp_path).evaluate(
        file_task(),
        AgentResult("requirements", "success", summary="already existed"),
    )

    assert report.passed is False
    assert "missing_run_provenance" in report.failures[0]


def test_file_acceptance_requires_file_and_current_tool_artifact(tmp_path):
    (tmp_path / "requirements.md").write_text("current", encoding="utf-8")
    result = AgentResult(
        "requirements",
        "success",
        artifacts=["requirements.md"],
        tool_records=[
            {
                "tool": "file_editor",
                "success": True,
                "metadata": {"artifacts": ["requirements.md"]},
            }
        ],
    )

    report = AcceptanceEvaluator(tmp_path).evaluate(file_task(), result)

    assert report.passed is True


def test_directory_output_accepts_a_run_provenanced_child_file(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok(): pass", encoding="utf-8")
    task = SubTask(
        "tests",
        "tester",
        "write tests",
        metadata={
            "expected_outputs": ["tests/"],
            "checks": [{"id": "tests_created", "check_type": "file_exists"}],
        },
    )
    result = AgentResult("tests", "success", artifacts=["tests\\test_app.py"])

    report = AcceptanceEvaluator(tmp_path).evaluate(task, result)

    assert report.passed is True
