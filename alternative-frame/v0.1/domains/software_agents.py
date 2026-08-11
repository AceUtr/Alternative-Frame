from __future__ import annotations

import ast
import difflib
from dataclasses import dataclass
from typing import Any, Mapping

from core.agents import Agent, AgentRegistry
from core.models import AgentResult, SubTask


PYTEST_COMMAND = "python -m pytest test_app.py -q -p no:cacheprovider"


@dataclass
class SoftwareRunState:
    before_code: str = ""
    after_code: str = ""
    test_output: str = ""
    test_exit_code: int | None = None


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
    result = tools.execute(
        "file_editor",
        {"action": "write", "path": path, "content": content},
    )
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


def _rewrite_add_implementation(source: str, operator: ast.operator) -> str:
    tree = ast.parse(source)

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != "add":
            continue

        argument_names = [argument.arg for argument in node.args.args]
        if argument_names[:2] != ["a", "b"]:
            continue

        node.body = [
            ast.Return(
                value=ast.BinOp(
                    left=ast.Name(id="a", ctx=ast.Load()),
                    op=operator,
                    right=ast.Name(id="b", ctx=ast.Load()),
                )
            )
        ]
        ast.fix_missing_locations(tree)
        return ast.unparse(tree) + "\n"

    raise ValueError("fixture does not define add(a, b)")


class SoftwareAgent(Agent):
    """Domain agent that owns its own tools and returns AgentResult directly."""

    def __init__(self, role: str, tools, state: SoftwareRunState):
        self.role = role
        self.tools = tools
        self.state = state
        self.retry_feedback: list[dict[str, Any]] = []

    def run(
        self,
        task: SubTask,
        context: Mapping[str, AgentResult],
    ) -> AgentResult:
        feedback = task.metadata.get("retry_feedback")
        if isinstance(feedback, dict):
            self.retry_feedback.append(feedback)

        return software_handler(task, self.tools, self.state)


def software_handler(task: SubTask, tools, state: SoftwareRunState) -> AgentResult:
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
        write, write_record = _write_file(
            tools,
            "artifacts/requirement_analysis.md",
            analysis,
        )
        if not write.success:
            return _failed(
                task,
                "Failed to write requirement analysis",
                [write.error],
                tool_records=[read_req, read_code, write_record],
            )

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
        write, write_record = _write_file(
            tools,
            "artifacts/architecture_design.md",
            architecture,
        )
        if not write.success:
            return _failed(
                task,
                "Failed to write architecture design",
                [write.error],
                tool_records=[write_record],
            )

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
        state.test_output = test_result.output or test_result.error or ""
        state.test_exit_code = test_result.exit_code

        if task.id == "diagnose_failure":
            diagnosis = (
                "# Diagnosis\n\n"
                f"- Command: `{PYTEST_COMMAND}`\n"
                f"- Exit code: {state.test_exit_code}\n"
                "- Result: failing baseline captured before repair.\n"
            )
            write, write_record = _write_file(
                tools,
                "artifacts/diagnosis.md",
                diagnosis,
            )
            if not write.success:
                return _failed(
                    task,
                    "Failed to write diagnosis",
                    [write.error],
                    tool_records=[test_record, write_record],
                )

            status_note = (
                "failing baseline captured"
                if state.test_exit_code != 0
                else "baseline already passed"
            )
            return _success(
                task,
                status_note,
                artifacts=write.metadata.get("artifacts", []),
                evidence=["baseline_test_executed"],
                tool_records=[test_record, write_record],
            )

        if test_result.success and state.test_exit_code == 0:
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
            [state.test_output],
            evidence=["pytest_failed"],
            tool_records=[test_record],
        )

    if task.role == "developer":
        code, read_record = _read_file(tools, "app.py")
        state.before_code = state.before_code or code

        attempt = int(task.metadata.get("runtime_attempt", 1))
        fault_scenario = task.metadata.get("fault_scenario", "none")

        if fault_scenario == "retry-once" and attempt == 1:
            repaired = _rewrite_add_implementation(code, ast.Mult())
        else:
            repaired = _rewrite_add_implementation(code, ast.Add())

        write, write_record = _write_file(tools, "app.py", repaired)
        state.after_code = repaired

        if not write.success:
            return _failed(
                task,
                "Failed to write repaired source",
                [write.error],
                tool_records=[read_record, write_record],
            )

        test_result, test_record = _run_tests(tools)
        state.test_output = test_result.output or test_result.error or ""
        state.test_exit_code = test_result.exit_code

        records = [read_record, write_record, test_record]
        artifacts = write.metadata.get("artifacts", [])

        if test_result.success and state.test_exit_code == 0:
            evidence = ["source_updated", "pytest_pass"]
            if task.metadata.get("retry_feedback"):
                evidence.append("retry_feedback_received")

            return _success(
                task,
                "Source code modified and exact tests passed",
                artifacts=artifacts,
                evidence=evidence,
                tool_records=records,
            )

        return _failed(
            task,
            "Source code modified but exact tests failed",
            [state.test_output],
            artifacts=artifacts,
            evidence=["source_updated", "pytest_failed"],
            tool_records=records,
        )

    if task.role == "reviewer":
        code, read_record = _read_file(tools, "app.py")
        if "return a + b" in code:
            return _success(
                task,
                "Code review verified the repaired implementation uses `return a + b`.",
                evidence=["review_complete"],
                tool_records=[read_record],
            )

        return _failed(
            task,
            "Code review found the repair incomplete",
            ["expected `return a + b`"],
            tool_records=[read_record],
        )

    if task.role == "reporter":
        current_code, read_record = _read_file(tools, "app.py")
        if not state.after_code:
            state.after_code = current_code

        diff = "\n".join(
            difflib.unified_diff(
                (state.before_code or "").splitlines(),
                current_code.splitlines(),
                fromfile="before/app.py",
                tofile="after/app.py",
                lineterm="",
            )
        )

        status = "PASS" if state.test_exit_code == 0 else "FAILED"
        report = (
            "# Software Engineering Agent Report\n\n"
            "## Execution Evidence\n\n"
            f"- Status: {status}\n"
            "- Modified file: `app.py`\n"
            f"- Test command: `{PYTEST_COMMAND}`\n"
            f"- Test exit code: {state.test_exit_code}\n\n"
            "## Diff\n\n"
            "```diff\n"
            f"{diff}\n"
            "```\n\n"
            "## Test Output\n\n"
            "```text\n"
            f"{state.test_output.strip()}\n"
            "```\n"
        )

        report_write, report_record = _write_file(
            tools,
            "artifacts/software_report.md",
            report,
        )
        diff_write, diff_record = _write_file(
            tools,
            "artifacts/code_diff.patch",
            diff,
        )
        log_write, log_record = _write_file(
            tools,
            "artifacts/test_log.txt",
            state.test_output,
        )

        records = [read_record, report_record, diff_record, log_record]
        failures = [
            item.error
            for item in (report_write, diff_write, log_write)
            if not item.success
        ]
        if failures:
            return _failed(
                task,
                "Failed to write software report artifacts",
                failures,
                tool_records=records,
            )

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

    return _failed(
        task,
        f"Unsupported software role: {task.role}",
        [f"unknown role {task.role}"],
    )


def build_software_agents(tools):
    registry = AgentRegistry()
    state = SoftwareRunState()

    for role in ("analyst", "architect", "developer", "tester", "reviewer", "reporter"):
        registry.register(SoftwareAgent(role, tools, state))

    return registry
