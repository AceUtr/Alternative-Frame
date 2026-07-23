from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import PurePosixPath
from typing import Callable, Dict, Optional

from ..model_client import OpenAICompatibleClient
from ..models import Plan, SubTask
from .acceptance_contract import AcceptanceContract, GoalCriterion
from .contract_planner import ContractCoverageValidator
from .replanner import DEFAULT_ROLE_TOOLS, PlanValidator, StructuredReplanner


class InitialPlanError(RuntimeError):
    pass


class ArtifactOwnershipValidator:
    """Require unique task ownership for contract artifacts and criteria."""

    @staticmethod
    def _path(value):
        return str(value or "").replace("\\", "/").rstrip("/")

    def validate(self, plan: Plan, contract: AcceptanceContract) -> Plan:
        criterion_owners: Dict[str, list] = {}
        artifact_owners: Dict[str, list] = {}
        for task in plan.subtasks:
            for criterion_id in task.metadata.get("contract_criteria", []):
                criterion_owners.setdefault(criterion_id, []).append(task.id)
            for output in task.metadata.get("expected_outputs", []):
                artifact_owners.setdefault(self._path(output), []).append(task.id)
        errors = []
        contract_artifacts = {
            self._path(item.path)
            for item in contract.criteria
            if item.check_type == "file_exists" and item.path
        }
        unrelated_artifacts = sorted(set(artifact_owners) - contract_artifacts)
        if unrelated_artifacts:
            errors.append(f"plan invents artifacts outside the confirmed contract: {unrelated_artifacts}")
        duplicated_criteria = {key: value for key, value in criterion_owners.items() if len(value) > 1}
        duplicated_artifacts = {key: value for key, value in artifact_owners.items() if len(value) > 1}
        if duplicated_criteria:
            errors.append(f"criteria have multiple owners: {duplicated_criteria}")
        if duplicated_artifacts:
            errors.append(f"artifacts have multiple creators: {duplicated_artifacts}")
        for criterion in contract.criteria:
            if criterion.required and criterion.check_type == "file_exists" and criterion.path:
                path = self._path(criterion.path)
                owners = artifact_owners.get(path, [])
                criterion_tasks = criterion_owners.get(criterion.id, [])
                if len(owners) != 1:
                    errors.append(f"artifact criterion {criterion.id} requires one creator for {path}")
                elif criterion_tasks != owners:
                    errors.append(
                        f"artifact criterion {criterion.id} owner {criterion_tasks} does not match creator {owners}"
                    )
        if errors:
            raise InitialPlanError("; ".join(errors))
        return plan


class RuleBasedContractPlanner:
    """Build a domain-neutral DAG directly from a confirmed contract."""

    GROUPS = OrderedDict(
        [
            ("implementation", ("developer", ["file_editor", "shell_runner"])),
            ("tests", ("tester", ["file_editor", "shell_runner", "test_runner"])),
            ("documents", ("reviewer", ["file_editor"])),
            ("experiment", ("experimenter", ["file_editor", "experiment_runner", "shell_runner"])),
            ("verification", ("tester", ["shell_runner", "test_runner"])),
            ("review", ("reviewer", ["file_editor", "test_runner"])),
        ]
    )

    def __init__(self, validator=None, coverage=None, ownership=None):
        self.validator = validator or PlanValidator()
        self.coverage = coverage or ContractCoverageValidator()
        self.ownership = ownership or ArtifactOwnershipValidator()

    def build(self, contract: AcceptanceContract, task_budget: int = 50) -> Plan:
        grouped = {name: [] for name in self.GROUPS}
        path_groups = {}
        for criterion in contract.criteria:
            group = self._group_for(criterion)
            grouped[group].append(criterion)
            if criterion.check_type == "file_exists" and criterion.path:
                path_groups[self._path(criterion.path)] = group

        # Keep qualitative checks about a concrete artifact with its creator/test owner.
        for criterion in list(grouped["review"]):
            if criterion.path and self._path(criterion.path) in path_groups:
                target = path_groups[self._path(criterion.path)]
                if target != "review":
                    grouped["review"].remove(criterion)
                    grouped[target].append(criterion)

        tasks = []
        group_ids = {}
        for group, (role, tools) in self.GROUPS.items():
            criteria = grouped[group]
            if not criteria:
                continue
            task_id = {
                "implementation": "implement_contract_artifacts",
                "tests": "create_contract_tests",
                "documents": "create_contract_documents",
                "experiment": "run_contract_experiments",
                "verification": "verify_contract_commands",
                "review": "review_contract_semantics",
            }[group]
            group_ids[group] = task_id
            checks = [self._check(item) for item in criteria]
            outputs = list(dict.fromkeys(
                item.path for item in criteria if item.check_type == "file_exists" and item.path
            ))
            tasks.append(
                SubTask(
                    id=task_id,
                    role=role,
                    description=self._description(group, criteria),
                    acceptance=[item.id for item in criteria],
                    max_retries=2,
                    metadata={
                        "required_tools": list(tools),
                        "expected_outputs": outputs,
                        "checks": checks,
                        "contract_criteria": [item.id for item in criteria],
                    },
                )
            )

        task_map = {task.id: task for task in tasks}
        producer_ids = [
            group_ids[name]
            for name in ("implementation", "tests", "documents", "experiment")
            if name in group_ids
        ]
        if "tests" in group_ids and "implementation" in group_ids:
            task_map[group_ids["tests"]].depends_on = [group_ids["implementation"]]
        if "documents" in group_ids and "implementation" in group_ids:
            task_map[group_ids["documents"]].depends_on = [group_ids["implementation"]]
        if "experiment" in group_ids and "implementation" in group_ids:
            task_map[group_ids["experiment"]].depends_on = [group_ids["implementation"]]
        if "verification" in group_ids:
            task_map[group_ids["verification"]].depends_on = list(producer_ids)
        if "review" in group_ids:
            predecessors = [group_ids["verification"]] if "verification" in group_ids else producer_ids
            task_map[group_ids["review"]].depends_on = list(predecessors)

        plan = Plan(
            goal=contract.goal,
            subtasks=tasks,
            final_acceptance=[item.id for item in contract.criteria if item.required],
        )
        self.validator.validate(plan, task_budget)
        self.coverage.validate(plan, contract)
        self.ownership.validate(plan, contract)
        return plan

    def _group_for(self, criterion: GoalCriterion) -> str:
        if criterion.check_type == "command":
            return "verification"
        if criterion.check_type == "metric":
            return "experiment"
        if criterion.check_type == "file_exists" and criterion.path:
            path = PurePosixPath(self._path(criterion.path))
            lowered = str(path).lower()
            if "test" in lowered or path.name.startswith("test_"):
                return "tests"
            if path.suffix.lower() in {".md", ".rst"}:
                return "documents"
            return "implementation"
        lowered = criterion.description.lower()
        if "test" in lowered or "测试" in criterion.description:
            return "tests"
        if any(word in lowered for word in ("readme", "document", "report")) or any(
            word in criterion.description for word in ("文档", "报告")
        ):
            return "documents"
        if any(word in lowered for word in ("metric", "experiment")) or any(
            word in criterion.description for word in ("指标", "实验")
        ):
            return "experiment"
        return "review"

    @staticmethod
    def _path(value):
        return str(value).replace("\\", "/")

    @staticmethod
    def _check(item):
        return {
            "id": item.id,
            "description": item.description,
            "check_type": item.check_type,
            "required": item.required,
            "path": item.path,
            "command": item.command,
            "metric_name": item.metric_name,
            "threshold": item.threshold,
        }

    @staticmethod
    def _description(group, criteria):
        requirements = "\n".join(
            f"- [{item.id}] {item.description}"
            + (f" Exact path: {item.path}." if item.path else "")
            + (f" Exact command: {item.command}." if item.command else "")
            for item in criteria
        )
        return (
            f"Complete the {group} portion of the confirmed acceptance contract. "
            "Use the exact paths and commands below; do not invent unrelated product features.\n"
            f"{requirements}"
        )


class StructuredInitialDAGGenerator:
    """Generate a contract-native initial DAG with deterministic fallback."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        fallback=None,
        validator=None,
        coverage=None,
        ownership=None,
        max_attempts: int = 2,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        self.client = client
        self.fallback = fallback or RuleBasedContractPlanner()
        self.validator = validator or PlanValidator()
        self.coverage = coverage or ContractCoverageValidator()
        self.ownership = ownership or ArtifactOwnershipValidator()
        self.max_attempts = max_attempts
        self.on_event = on_event

    def generate(self, contract: AcceptanceContract, task_budget: int = 50) -> Plan:
        messages = self._messages(contract, task_budget)
        last_error = "no initial plan response"
        for attempt in range(1, self.max_attempts + 1):
            self._emit("initial_plan_started", {"attempt": attempt})
            content = ""
            try:
                response = self.client.chat(messages)
                content = response.get("content", "") if isinstance(response, dict) else str(response)
                payload = json.loads(content)
                plan = StructuredReplanner._build_plan(payload)
                for task, raw in zip(plan.subtasks, payload["tasks"]):
                    task.metadata["contract_criteria"] = list(raw.get("contract_criteria", []))
                plan.goal = contract.goal
                plan.final_acceptance = [item.id for item in contract.criteria if item.required]
                self.validator.validate(plan, task_budget)
                self.coverage.validate(plan, contract)
                self.ownership.validate(plan, contract)
                self._emit("initial_plan_completed", {"attempt": attempt, "task_count": len(plan.subtasks)})
                return plan
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._emit("initial_plan_validation_failed", {"attempt": attempt, "error": last_error})
                if attempt < self.max_attempts:
                    messages.extend([
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": f"Rejected: {last_error}. Return corrected strict JSON only."},
                    ])
        plan = self.fallback.build(contract, task_budget)
        self._emit("initial_plan_fallback", {"reason": last_error, "task_count": len(plan.subtasks)})
        return plan

    def _messages(self, contract, task_budget):
        return [
            {
                "role": "system",
                "content": (
                    "Generate the initial multi-agent DAG directly from the confirmed contract. Return strict JSON only. "
                    "Do not use generic authentication templates or invent unrelated files. Every criterion must have "
                    "exactly one owner and every file artifact exactly one creator."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "goal": contract.goal,
                    "acceptance_contract": contract.to_dict(),
                    "task_budget": task_budget,
                    "allowed_role_tools": {role: sorted(tools) for role, tools in DEFAULT_ROLE_TOOLS.items()},
                    "required_schema": {
                        "phase_goal": "string",
                        "tasks": [{
                            "id": "unique_id", "role": "allowed role", "description": "specific work",
                            "depends_on": ["task_id"], "required_tools": ["allowed tool"],
                            "expected_outputs": ["exact relative path"],
                            "contract_criteria": ["criterion_id"],
                            "checks": [{"id": "criterion_id", "check_type": "file_exists|command|metric|semantic|manual", "path": None, "command": None}],
                            "max_retries": 2,
                        }],
                        "final_acceptance": ["required criterion id"],
                    },
                }, ensure_ascii=False),
            },
        ]

    def _emit(self, event, payload):
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass
