from __future__ import annotations

import json
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Callable, Dict, Mapping, Optional, Set

from ..model_client import OpenAICompatibleClient
from ..models import Plan, SubTask
from .evaluator import GoalEvaluation
from .state import LongHorizonState


DEFAULT_ROLE_TOOLS: Dict[str, Set[str]] = {
    "researcher": {"file_editor", "experiment_runner"},
    "experimenter": {"file_editor", "experiment_runner", "shell_runner"},
    "reviewer": {"file_editor", "test_runner", "git_client"},
    "analyst": {"file_editor"},
    "architect": {"file_editor"},
    "developer": {"file_editor", "shell_runner", "git_client", "test_runner"},
    "tester": {"file_editor", "shell_runner", "test_runner"},
}


class PlanValidationError(ValueError):
    pass


class StructuredReplanError(RuntimeError):
    pass


class PlanValidator:
    TASK_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    CHECK_TYPES = {"manual", "command", "file_exists", "metric"}

    def __init__(self, role_tools: Optional[Mapping[str, Set[str]]] = None):
        source = role_tools or DEFAULT_ROLE_TOOLS
        self.role_tools = {role: set(tools) for role, tools in source.items()}

    def validate(self, plan: Plan, remaining_task_budget: int) -> Plan:
        errors = []
        if not plan.subtasks:
            errors.append("plan must contain at least one task")
        if len(plan.subtasks) > remaining_task_budget:
            errors.append(
                f"plan has {len(plan.subtasks)} tasks but remaining budget is {remaining_task_budget}"
            )
        for task in plan.subtasks:
            if not self.TASK_ID_PATTERN.fullmatch(task.id):
                errors.append(f"invalid task id: {task.id!r}")
            if task.role not in self.role_tools:
                errors.append(f"unknown role for {task.id}: {task.role}")
                allowed_tools = set()
            else:
                allowed_tools = self.role_tools[task.role]
            if not task.description.strip():
                errors.append(f"task {task.id} has an empty description")
            if len(task.description) > 4000:
                errors.append(f"task {task.id} description exceeds 4000 characters")
            required_tools = set(task.metadata.get("required_tools", []))
            forbidden = required_tools - allowed_tools
            if forbidden:
                errors.append(
                    f"task {task.id} role {task.role} cannot use tools: {sorted(forbidden)}"
                )
            for output in task.metadata.get("expected_outputs", []):
                if not self._safe_relative_path(output):
                    errors.append(f"task {task.id} has unsafe output path: {output!r}")
            checks = task.metadata.get("checks", [])
            if not checks:
                errors.append(f"task {task.id} must declare at least one acceptance check")
            for check in checks:
                check_id = check.get("id")
                check_type = check.get("check_type")
                if not check_id or check_type not in self.CHECK_TYPES:
                    errors.append(f"task {task.id} has an invalid acceptance check")
                if check_type == "command":
                    command = check.get("command")
                    if not isinstance(command, str) or not command.strip() or "\n" in command:
                        errors.append(f"task {task.id} command check must contain one command line")
        try:
            plan.validate()
        except ValueError as exc:
            errors.append(str(exc))
        if errors:
            raise PlanValidationError("; ".join(errors))
        return plan

    @staticmethod
    def _safe_relative_path(value: Any) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        windows = PureWindowsPath(value)
        posix = PurePosixPath(value)
        return not windows.is_absolute() and not posix.is_absolute() and ".." not in windows.parts and ".." not in posix.parts


class StructuredReplanner:
    """Ask a model for a strict JSON recovery DAG, then validate it before use."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        validator: Optional[PlanValidator] = None,
        max_attempts: int = 2,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.client = client
        self.validator = validator or PlanValidator()
        self.max_attempts = max_attempts
        self.on_event = on_event

    def _emit(self, event: str, payload: dict) -> None:
        if not self.on_event:
            return
        try:
            self.on_event(event, payload)
        except Exception:
            # Observability must not invalidate an otherwise safe plan.
            pass

    def __call__(self, state: LongHorizonState, evaluation: GoalEvaluation) -> Optional[Plan]:
        return self.replan(state, evaluation)

    def replan(self, state: LongHorizonState, evaluation: GoalEvaluation) -> Plan:
        remaining_tasks = state.max_total_tasks - state.total_tasks
        remaining_phases = state.max_phases - state.phase
        if remaining_tasks < 1 or remaining_phases < 1:
            raise StructuredReplanError("no long-horizon budget remains for replanning")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the recovery planner for a long-horizon multi-agent system. "
                    "Return one strict JSON object only. Do not use Markdown or prose. "
                    "Create the smallest recovery DAG needed to address the previous evaluation. "
                    "Use only the supplied roles and each role's allowed tools."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "goal": state.goal,
                        "next_phase": state.phase + 1,
                        "remaining_budget": {
                            "phases": remaining_phases,
                            "tasks": remaining_tasks,
                        },
                        "completed_tasks": state.completed_tasks,
                        "failed_tasks": state.failed_tasks,
                        "artifacts": state.artifacts,
                        "decisions": state.decisions[-10:],
                        "previous_evaluation": evaluation.to_dict(),
                        "allowed_role_tools": {
                            role: sorted(tools) for role, tools in self.validator.role_tools.items()
                        },
                        "required_schema": {
                            "phase_goal": "string",
                            "tasks": [
                                {
                                    "id": "unique_identifier",
                                    "role": "allowed_role",
                                    "description": "specific recovery work",
                                    "depends_on": ["task_id"],
                                    "required_tools": ["allowed_tool"],
                                    "expected_outputs": ["relative/path"],
                                    "checks": [
                                        {
                                            "id": "check_id",
                                            "check_type": "manual|command|file_exists|metric",
                                            "command": "required only for command checks",
                                        }
                                    ],
                                    "max_retries": 0,
                                }
                            ],
                            "final_acceptance": ["check_id"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

        last_error = "model did not return a plan"
        for attempt in range(1, self.max_attempts + 1):
            self._emit("replan_started", {"attempt": attempt, "phase": state.phase + 1})
            response = self.client.chat(messages)
            content = response.get("content", "") if isinstance(response, dict) else str(response)
            try:
                payload = self._parse_json(content)
                plan = self._build_plan(payload)
                self.validator.validate(plan, remaining_tasks)
                self._emit(
                    "replan_completed",
                    {"attempt": attempt, "phase_goal": plan.goal, "task_count": len(plan.subtasks)},
                )
                return plan
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, PlanValidationError) as exc:
                last_error = str(exc)
                self._emit("replan_validation_failed", {"attempt": attempt, "error": last_error})
                if attempt < self.max_attempts:
                    messages.extend(
                        [
                            {"role": "assistant", "content": content},
                            {
                                "role": "user",
                                "content": (
                                    f"The plan was rejected: {last_error}. "
                                    "Return a corrected strict JSON object only."
                                ),
                            },
                        ]
                    )
        raise StructuredReplanError(
            f"model failed to produce a valid recovery plan after {self.max_attempts} attempts: {last_error}"
        )

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty model response")
        payload = json.loads(content.strip())
        if not isinstance(payload, dict):
            raise ValueError("replanner response must be a JSON object")
        return payload

    @staticmethod
    def _build_plan(payload: Dict[str, Any]) -> Plan:
        phase_goal = payload["phase_goal"]
        tasks_data = payload["tasks"]
        if not isinstance(phase_goal, str) or not isinstance(tasks_data, list):
            raise ValueError("phase_goal must be a string and tasks must be a list")
        subtasks = []
        for item in tasks_data:
            checks = item.get("checks", [])
            subtasks.append(
                SubTask(
                    id=item["id"],
                    role=item["role"],
                    description=item["description"],
                    depends_on=list(item.get("depends_on", [])),
                    acceptance=[check["id"] for check in checks],
                    max_retries=max(0, min(2, int(item.get("max_retries", 0)))),
                    metadata={
                        "required_tools": list(item.get("required_tools", [])),
                        "expected_outputs": list(item.get("expected_outputs", [])),
                        "checks": checks,
                    },
                )
            )
        return Plan(
            goal=phase_goal,
            subtasks=subtasks,
            final_acceptance=list(payload.get("final_acceptance", [])),
        )
