from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Dict, List

from ..models import Plan, SubTask
from .acceptance_contract import AcceptanceContract, GoalCriterion
from .replanner import PlanValidationError, PlanValidator


class ContractCoverageError(PlanValidationError):
    pass


class ContractCoverageValidator:
    """Require every mandatory contract criterion to be owned by the initial DAG."""

    def validate(self, plan: Plan, contract: AcceptanceContract) -> Plan:
        owners: Dict[str, List[str]] = {}
        for task in plan.subtasks:
            for criterion_id in task.metadata.get("contract_criteria", []):
                owners.setdefault(criterion_id, []).append(task.id)
        required = {item.id for item in contract.criteria if item.required}
        missing = sorted(required - set(owners))
        unknown = sorted(set(owners) - {item.id for item in contract.criteria})
        if missing or unknown:
            details = []
            if missing:
                details.append(f"required criteria without task owners: {missing}")
            if unknown:
                details.append(f"tasks reference unknown contract criteria: {unknown}")
            raise ContractCoverageError("; ".join(details))
        return plan


class ContractAwarePlanner:
    """Turn a confirmed contract plus a domain baseline into an executable initial DAG."""

    def __init__(self, plan_validator=None, coverage_validator=None):
        self.plan_validator = plan_validator or PlanValidator()
        self.coverage_validator = coverage_validator or ContractCoverageValidator()

    def build(self, contract: AcceptanceContract, baseline: Plan, task_budget: int = 50) -> Plan:
        if baseline.goal.strip() != contract.goal.strip():
            raise ValueError("baseline goal does not match acceptance contract")
        tasks = [deepcopy(task) for task in baseline.subtasks]
        for task in tasks:
            task.metadata["contract_criteria"] = []

        for criterion in contract.criteria:
            owner = self._select_owner(tasks, criterion)
            if owner is None:
                owner = self._verification_task(tasks, criterion)
                tasks.append(owner)
            owner.metadata.setdefault("contract_criteria", []).append(criterion.id)
            self._attach_check(owner, criterion)

        plan = Plan(
            goal=contract.goal,
            subtasks=tasks,
            final_acceptance=[item.id for item in contract.criteria if item.required],
        )
        self.plan_validator.validate(plan, task_budget)
        self.coverage_validator.validate(plan, contract)
        return plan

    def _select_owner(self, tasks: List[SubTask], criterion: GoalCriterion):
        if criterion.check_type == "command":
            return self._last(tasks, lambda task: task.role == "tester")
        if criterion.check_type == "metric":
            return self._last(tasks, lambda task: task.role == "experimenter")
        if criterion.check_type in {"semantic", "manual"}:
            return self._last(tasks, lambda task: task.role == "reviewer")
        if criterion.check_type == "file_exists" and criterion.path:
            wanted = PurePosixPath(criterion.path.replace("\\", "/"))
            for task in tasks:
                for output in task.metadata.get("expected_outputs", []):
                    candidate = PurePosixPath(str(output).replace("\\", "/"))
                    if candidate == wanted or candidate in wanted.parents or wanted in candidate.parents:
                        return task
            suffix = wanted.suffix.lower()
            if "test" in wanted.parts or wanted.name.startswith("test_"):
                return self._last(tasks, lambda task: task.role == "tester")
            if suffix in {".md", ".rst", ".txt"}:
                return self._last(tasks, lambda task: task.role in {"reviewer", "analyst"})
            return self._last(tasks, lambda task: task.role in {"developer", "experimenter"})
        return None

    @staticmethod
    def _last(tasks, predicate):
        matches = [task for task in tasks if predicate(task)]
        return matches[-1] if matches else None

    def _verification_task(self, tasks: List[SubTask], criterion: GoalCriterion) -> SubTask:
        role = "reviewer"
        tools = ["file_editor"]
        if criterion.check_type == "command":
            role, tools = "tester", ["shell_runner", "test_runner"]
        elif criterion.check_type == "metric":
            role, tools = "experimenter", ["experiment_runner"]
        elif criterion.check_type == "file_exists":
            role, tools = "developer", ["file_editor"]
        dependencies = [task.id for task in tasks if not any(task.id in other.depends_on for other in tasks)]
        return SubTask(
            id=f"contract_{criterion.id}",
            role=role,
            description=f"完成并验证合同标准 {criterion.id}：{criterion.description}",
            depends_on=dependencies,
            acceptance=[criterion.id],
            max_retries=1,
            metadata={
                "required_tools": tools,
                "expected_outputs": [criterion.path] if criterion.path else [],
                "checks": [],
                "contract_criteria": [],
            },
        )

    @staticmethod
    def _attach_check(task: SubTask, criterion: GoalCriterion) -> None:
        checks = task.metadata.setdefault("checks", [])
        checks = [check for check in checks if check.get("id") != criterion.id]
        checks.append(
            {
                "id": criterion.id,
                "description": criterion.description,
                "check_type": criterion.check_type,
                "required": criterion.required,
                "path": criterion.path,
                "command": criterion.command,
                "metric_name": criterion.metric_name,
                "threshold": criterion.threshold,
            }
        )
        task.metadata["checks"] = checks
        if criterion.id not in task.acceptance:
            task.acceptance.append(criterion.id)
        if criterion.path and criterion.path not in task.metadata.setdefault("expected_outputs", []):
            task.metadata["expected_outputs"].append(criterion.path)
