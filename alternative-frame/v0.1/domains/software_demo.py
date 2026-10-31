"""Reproducible software-engineering domain adapter."""

from __future__ import annotations

import ast
import json
import importlib.util
from pathlib import Path
from typing import Any, Mapping

from core.agents import Agent
from core.domains import DomainAdapter
from core.long_horizon import AcceptanceContract, GoalCriterion
from core.models import AgentResult, Plan, SubTask, utc_now
from core.tools import FileEditor, ShellRunner, TestRunner, Tool, ToolRegistry, ToolResult


EXACT_TEST_COMMAND = "python -m pytest test_app.py -q -p no:cacheprovider"
DEFAULT_GOAL = "Repair the supplied buggy application and prove the exact test command passes"


class PythonAstRepairTool(Tool):
    """Change one function's returned binary operator without string replacement."""

    name = "python_ast_repair"
    _operators = {"add": ast.Add, "subtract": ast.Sub, "multiply": ast.Mult}

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Repair the returned binary operator in a Python function",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "function": {"type": "string"},
                        "operator": {"type": "string", "enum": sorted(self._operators)},
                    },
                    "required": ["path", "function", "operator"],
                },
            },
        }

    def _safe(self, value: str) -> Path:
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"path escapes workspace: {value}")
        target = (self.workspace / relative).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise ValueError(f"path escapes workspace: {value}")
        return target

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = self._safe(str(arguments.get("path", "")))
        function_name = str(arguments.get("function", ""))
        operator_name = str(arguments.get("operator", ""))
        operator_type = self._operators.get(operator_name)
        if not path.is_file() or path.suffix != ".py":
            return ToolResult(self.name, False, error=f"Python file not found: {path.name}")
        if not function_name or operator_type is None:
            return ToolResult(self.name, False, error="function or operator is invalid")

        tree = ast.parse(path.read_text(encoding="utf-8"))
        changed = False
        previous = ""
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != function_name:
                continue
            for statement in node.body:
                if isinstance(statement, ast.Return) and isinstance(statement.value, ast.BinOp):
                    previous = type(statement.value.op).__name__
                    statement.value.op = operator_type()
                    changed = True
                    break
        if not changed:
            return ToolResult(self.name, False, error=f"repairable return not found in {function_name}")

        path.write_text(ast.unparse(ast.fix_missing_locations(tree)) + "\n", encoding="utf-8")
        # A same-size repair performed within one filesystem timestamp tick can
        # leave Python's timestamp-based bytecode cache looking valid.
        cache_path = Path(importlib.util.cache_from_source(str(path)))
        if cache_path.is_file():
            cache_path.unlink()
        relative = path.relative_to(self.workspace).as_posix()
        return ToolResult(
            self.name,
            True,
            output=f"changed {function_name} operator from {previous} to {operator_type.__name__}",
            metadata={"artifacts": [relative], "previous_operator": previous, "operator": operator_name},
        )


def _record(result: ToolResult, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": result.tool,
        "arguments": dict(arguments),
        "success": result.success,
        "exit_code": result.exit_code,
        "duration_seconds": result.duration_seconds,
        "metadata": dict(result.metadata),
        "output_excerpt": (result.output or result.error)[:1200],
    }


class SoftwareExecutionAgent(Agent):
    def __init__(self, role: str, tools: ToolRegistry):
        self.role = role
        self.tools = tools

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        started = utc_now()
        action = str(task.metadata.get("action", ""))
        records: list[dict[str, Any]] = []
        artifacts: list[str] = []
        evidence: list[str] = []
        failures: list[str] = []

        if action == "diagnose":
            for path in ("requirements.md", "app.py", "test_app.py"):
                args = {"action": "read", "path": path}
                result = self.tools.execute("file_editor", args)
                records.append(_record(result, args))
                if not result.success:
                    failures.append(result.error)
            test_args = {"command": EXACT_TEST_COMMAND}
            baseline = self.tools.execute("test_runner", test_args)
            records.append(_record(baseline, test_args))
            if baseline.success:
                failures.append("fixture is not defective: baseline test unexpectedly passed")
            diagnosis = {
                "status": "confirmed",
                "observed_test_exit_code": baseline.exit_code,
                "fault": "add returns subtraction instead of addition",
                "repair": {"path": "app.py", "function": "add", "operator": "add"},
            }
            write_args = {
                "action": "write",
                "path": "artifacts/diagnosis.json",
                "content": json.dumps(diagnosis, indent=2),
            }
            written = self.tools.execute("file_editor", write_args)
            records.append(_record(written, write_args))
            if written.success:
                artifacts.append("artifacts/diagnosis.json")
                evidence.append(f"baseline_exit_code={baseline.exit_code}")
            else:
                failures.append(written.error)
        elif action == "repair":
            args = {"path": "app.py", "function": "add", "operator": "add"}
            result = self.tools.execute("python_ast_repair", args)
            records.append(_record(result, args))
            artifacts.extend(result.metadata.get("artifacts", []))
            evidence.append(result.output or result.error)
            if not result.success:
                failures.append(result.error)
        elif action == "verify":
            args = {"command": EXACT_TEST_COMMAND}
            result = self.tools.execute("test_runner", args)
            records.append(_record(result, args))
            evidence.append(f"exact_test_exit_code={result.exit_code}")
            if not result.success:
                failures.append(result.error or result.output or "exact test command failed")
        elif action == "report":
            verification = context.get("verify_fix")
            test_record = next(
                (record for record in (verification.tool_records if verification else []) if record.get("tool") == "test_runner"),
                {},
            )
            report = "\n".join([
                "# Software Repair Report", "", "- Modified file: `app.py`",
                "- Repair method: Python AST operator update (`Sub` to `Add`)",
                f"- Exact test command: `{test_record.get('arguments', {}).get('command', '')}`",
                f"- Exit code: `{test_record.get('exit_code')}`",
                f"- Passed: `{test_record.get('metadata', {}).get('passed_count', 0)}`",
                "- Remaining risk: this fixture validates a small arithmetic repair, not arbitrary repository repair.", "",
            ])
            args = {"action": "write", "path": "artifacts/software_report.md", "content": report}
            result = self.tools.execute("file_editor", args)
            records.append(_record(result, args))
            if result.success:
                artifacts.append("artifacts/software_report.md")
            else:
                failures.append(result.error)
        else:
            failures.append(f"unsupported software action: {action}")

        return AgentResult(
            subtask_id=task.id,
            status="failed" if failures else "success",
            summary="; ".join(failures) if failures else f"{action} completed with verifiable tool evidence",
            artifacts=list(dict.fromkeys(artifacts)), evidence=evidence, tool_records=records,
            failures=failures, started_at=started, finished_at=utc_now(),
        )


class SoftwareDomainAdapter(DomainAdapter):
    name = "software"

    def register_tools(self, registry: ToolRegistry, workspace: Path) -> None:
        shell = ShellRunner(workspace, timeout_seconds=60)
        registry.register(FileEditor(workspace))
        registry.register(shell)
        registry.register(TestRunner(shell))
        registry.register(PythonAstRepairTool(workspace))

    def build_agents(self, model_client, tools: ToolRegistry):
        return [SoftwareExecutionAgent(role, tools) for role in ("analyst", "developer", "tester", "reporter")]

    def build_plan(self, goal: str) -> Plan:
        return Plan(goal, [SubTask(
            "diagnose_failure", "analyst", "Read the fixture and prove the baseline failure", max_retries=0,
            metadata={"action": "diagnose", "required_tools": ["file_editor", "test_runner"],
                      "expected_outputs": ["artifacts/diagnosis.json"],
                      "checks": [{"id": "diagnosis", "check_type": "file_exists"}]},
        )], final_acceptance=[criterion.id for criterion in self.build_contract(goal).criteria])

    def build_recovery_plan(self, goal: str, missing_criteria: list[str] | None = None) -> Plan:
        return Plan(goal, [
            SubTask("implement_fix", "developer", "Apply the diagnosed repair through a workspace-scoped AST tool", max_retries=0,
                    metadata={"action": "repair", "required_tools": ["python_ast_repair"], "expected_outputs": ["app.py"],
                              "checks": [{"id": "source", "check_type": "file_exists"}]}),
            SubTask("verify_fix", "tester", "Run the exact contracted regression command", depends_on=["implement_fix"], max_retries=0,
                    metadata={"action": "verify", "required_tools": ["test_runner"], "expected_outputs": [],
                              "checks": [{"id": "tests", "check_type": "command", "command": EXACT_TEST_COMMAND}]}),
            SubTask("write_report", "reporter", "Build a report from the real test tool record", depends_on=["verify_fix"], max_retries=0,
                    metadata={"action": "report", "required_tools": ["file_editor"],
                              "expected_outputs": ["artifacts/software_report.md"],
                              "checks": [{"id": "report", "check_type": "file_exists"}]}),
        ], final_acceptance=[criterion.id for criterion in self.build_contract(goal).criteria])

    def build_contract(self, goal: str) -> AcceptanceContract:
        return AcceptanceContract(goal, [
            GoalCriterion("diagnosis", "Baseline failure was diagnosed", "file_exists", path="artifacts/diagnosis.json"),
            GoalCriterion("repaired_source", "The repaired source has current-run provenance", "file_exists", path="app.py"),
            GoalCriterion("exact_tests", "The exact regression command exits successfully", "command", command=EXACT_TEST_COMMAND),
            GoalCriterion("report", "A current-run evidence report exists", "file_exists", path="artifacts/software_report.md"),
        ], goal_summary="Diagnose, repair, test, and report a reproducible software defect",
           constraints=["offline", "workspace-scoped tools", "no prose-only completion"])

    def reset_workspace(self, workspace: Path) -> None:
        workspace = Path(workspace).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        artifacts = workspace / "artifacts"
        if artifacts.exists():
            for item in artifacts.iterdir():
                if item.is_file():
                    item.unlink()
        artifacts.mkdir(exist_ok=True)
        (workspace / "requirements.md").write_text("# Requirement\n\n`add(a, b)` must return the arithmetic sum.\n", encoding="utf-8")
        (workspace / "README.md").write_text("# Software fixture\n\nA deterministic offline repair target.\n", encoding="utf-8")
        (workspace / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (workspace / "test_app.py").write_text(
            "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n    assert add(-2, 5) == 3\n", encoding="utf-8")


def build(goal: str) -> Plan:
    return SoftwareDomainAdapter().build_plan(goal)
