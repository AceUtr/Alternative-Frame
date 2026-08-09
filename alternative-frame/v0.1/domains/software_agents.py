from __future__ import annotations

import difflib

from core.agents import AgentRegistry, DeterministicAgent
from core.models import AgentResult


PYTEST_COMMAND = "python -m pytest test_app.py -q -p no:cacheprovider"

BEFORE_CODE = ""
AFTER_CODE = ""
TEST_OUTPUT = ""
TEST_EXIT_CODE = None


def _record(tool_result, arguments=None):
    return {
        "tool": tool_result.tool,
        "arguments": arguments or {},
        "success": tool_result.success,
        "exit_code": tool_result.exit_code,
        "output_summary": (tool_result.output or tool_result.error or "")[-1000:],
        "metadata": tool_result.metadata,
    }


def _read_file(tools, path):
    result = tools.execute("file_editor", {"action": "read", "path": path})
    if not result.success:
        raise RuntimeError(result.error or result.output)
    return result.output, _record(result, {"action": "read", "path": path})


def _write_file(tools, path, content):
    result = tools.execute("file_editor", {"action": "write", "path": path, "content": content})
    return result, _record(result, {"action": "write", "path": path})


def _run_tests(tools):
    arguments = {"command": PYTEST_COMMAND}
    result = tools.execute("test_runner", arguments)
    return result, _record(result, arguments)


def _success(task, summary, artifacts=None, evidence=None, tool_records=None):
    return AgentResult(
        subtask_id=task.id,
        status="success",
        summary=summary,
        artifacts=artifacts or [],
        evidence=evidence or [],
        tool_records=tool_records or [],
    )


def _failed(task, summary, failures, artifacts=None, evidence=None, tool_records=None):
    return AgentResult(
        subtask_id=task.id,
        status="failed",
        summary=summary,
        artifacts=artifacts or [],
        evidence=evidence or [],
        tool_records=tool_records or [],
        failures=failures,
    )


def software_handler(task, context):
    global BEFORE_CODE, AFTER_CODE, TEST_OUTPUT, TEST_EXIT_CODE

    tools = context.get("tools")
    if tools is None:
        return _failed(task, "No tool registry was provided", ["missing tool registry"])

    if task.role == "analyst":
        requirements, read_req = _read_file(tools, "requirements.md")
        code, read_code = _read_file(tools, "app.py")
        analysis = (
            "# Requirement Analysis\n\n"
            "## Requirement\n\n"
            f"{requirements.strip()}\n\n"
            "## Observed Implementation\n\n"
            "The current `add(a, b)` implementation must be checked against the tests.\n\n"
            "```python\n"
            f"{code.strip()}\n"
            "```\n"
        )
        write, write_record = _write_file(tools, "artifacts/requirement_analysis.md", analysis)
        if not write.success:
            return _failed(task, "Failed to write requirement analysis", [write.error], tool_records=[read_req, read_code, write_record])
        return _success(
            task,
            "Requirement analysis generated",
            artifacts=write.metadata.get("artifacts", []),
            evidence=["requirement_analysis_generated"],
            tool_records=[read_req, read_code, write_record],
        )

    if task.role == "architect":
        architecture = (
            "# Architecture Design\n\n"
            "- `app.py` contains the calculator function under repair.\n"
            "- `test_app.py` contains executable regression tests.\n"
            "- `artifacts/` stores current-run analysis, diff, test log, and report evidence.\n"
        )
        write, write_record = _write_file(tools, "artifacts/architecture_design.md", architecture)
        if not write.success:
            return _failed(task, "Failed to write architecture design", [write.error], tool_records=[write_record])
        return _success(
            task,
            "Architecture design generated",
            artifacts=write.metadata.get("artifacts", []),
            evidence=["architecture_design_generated"],
            tool_records=[write_record],
        )

    if task.role == "tester":
        if (
            task.id == "run_targeted_tests"
            and task.metadata.get("fault_scenario") == "local-recovery"
            and not task.metadata.get("local_recovery_feedback")
        ):
            return _failed(
                task,
                "Injected local recovery failure before final regression evidence.",
                ["injected_local_recovery_failure"],
                evidence=["local_recovery_fault_injected"],
            )

        test_result, test_record = _run_tests(tools)
        TEST_OUTPUT = test_result.output or test_result.error
        TEST_EXIT_CODE = test_result.exit_code

        if task.id == "diagnose_failure":
            diagnosis = (
                "# Diagnosis\n\n"
                f"- Command: `{PYTEST_COMMAND}`\n"
                f"- Exit code: {TEST_EXIT_CODE}\n"
                "- Result: failing baseline captured before repair.\n"
            )
            write, write_record = _write_file(tools, "artifacts/diagnosis.md", diagnosis)
            status_note = "failing baseline captured" if TEST_EXIT_CODE != 0 else "baseline already passed"
            return _success(
                task,
                status_note,
                artifacts=write.metadata.get("artifacts", []) if write.success else [],
                evidence=["baseline_test_executed"],
                tool_records=[test_record, write_record],
            )

        if test_result.success and TEST_EXIT_CODE == 0:
            test_record["metadata"] = {
                **test_record.get("metadata", {}),
                "artifacts": ["test_app.py"],
            }
            return _success(
                task,
                "Regression tests passed",
                artifacts=["test_app.py"],
                evidence=["pytest_pass"],
                tool_records=[test_record],
            )
        return _failed(
            task,
            "Regression tests failed",
            [TEST_OUTPUT],
            evidence=["pytest_failed"],
            tool_records=[test_record],
        )

    if task.role == "developer":
        code, read_record = _read_file(tools, "app.py")
        BEFORE_CODE = BEFORE_CODE or code
        attempt = int(task.metadata.get("runtime_attempt", 1))

        if attempt == 1:
            repaired = code.replace("return b - a", "return a * b").replace("return a-b", "return a * b")
        else:
            repaired = (
                code.replace("return b - a", "return a + b")
                .replace("return a-b", "return a + b")
                .replace("return a * b", "return a + b")
                .replace("return a*b", "return a + b")
            )

        write, write_record = _write_file(tools, "app.py", repaired)
        AFTER_CODE = repaired
        if not write.success:
            return _failed(task, "Failed to write repaired source", [write.error], tool_records=[read_record, write_record])

        test_result, test_record = _run_tests(tools)
        TEST_OUTPUT = test_result.output or test_result.error
        TEST_EXIT_CODE = test_result.exit_code
        records = [read_record, write_record, test_record]
        artifacts = write.metadata.get("artifacts", [])

        if test_result.success and TEST_EXIT_CODE == 0:
            return _success(
                task,
                "Source code modified and exact tests passed",
                artifacts=artifacts,
                evidence=["source_updated", "pytest_pass"],
                tool_records=records,
            )
        return _failed(
            task,
            "Source code modified but exact tests failed",
            [TEST_OUTPUT],
            artifacts=artifacts,
            evidence=["source_updated", "pytest_failed"],
            tool_records=records,
        )

    if task.role == "reviewer":
        code, read_record = _read_file(tools, "app.py")
        if "return a + b" in code:
            review = "Code review verified the repaired implementation uses `return a + b`."
            return _success(task, review, evidence=["review_complete"], tool_records=[read_record])
        return _failed(task, "Code review found the repair incomplete", ["expected `return a + b`"], tool_records=[read_record])

    if task.role == "reporter":
        current_code, read_record = _read_file(tools, "app.py")
        if not AFTER_CODE:
            AFTER_CODE = current_code
        before = BEFORE_CODE or ""
        diff = "\n".join(
            difflib.unified_diff(
                before.splitlines(),
                current_code.splitlines(),
                fromfile="before/app.py",
                tofile="after/app.py",
                lineterm="",
            )
        )
        status = "PASS" if TEST_EXIT_CODE == 0 else "FAILED"
        report = (
            "# Software Engineering Agent Report\n\n"
            "## Execution Evidence\n\n"
            f"- Status: {status}\n"
            f"- Modified file: `app.py`\n"
            f"- Test command: `{PYTEST_COMMAND}`\n"
            f"- Test exit code: {TEST_EXIT_CODE}\n\n"
            "## Diff\n\n"
            "```diff\n"
            f"{diff}\n"
            "```\n\n"
            "## Test Output\n\n"
            "```text\n"
            f"{(TEST_OUTPUT or '').strip()}\n"
            "```\n"
        )
        report_write, report_record = _write_file(tools, "artifacts/software_report.md", report)
        diff_write, diff_record = _write_file(tools, "artifacts/code_diff.patch", diff)
        log_write, log_record = _write_file(tools, "artifacts/test_log.txt", TEST_OUTPUT or "")
        records = [read_record, report_record, diff_record, log_record]
        failures = [
            item.error
            for item in (report_write, diff_write, log_write)
            if not item.success
        ]
        if failures:
            return _failed(task, "Failed to write software report artifacts", failures, tool_records=records)
        return _success(
            task,
            "Software report generated from current-run test evidence",
            artifacts=[
                *report_write.metadata.get("artifacts", []),
                *diff_write.metadata.get("artifacts", []),
                *log_write.metadata.get("artifacts", []),
            ],
            evidence=["software_report_exists"],
            tool_records=records,
        )

    return _failed(task, f"Unsupported software role: {task.role}", [f"unknown role {task.role}"])


def build_software_agents():
    registry = AgentRegistry()
    for role in ("analyst", "architect", "developer", "tester", "reviewer", "reporter"):
        registry.register(DeterministicAgent(role=role, handler=software_handler))
    return registry

