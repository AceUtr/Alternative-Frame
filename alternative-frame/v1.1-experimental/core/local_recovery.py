from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Set

from .models import AgentResult, Plan, SubTask
from .orchestrator import Orchestrator, RunReport


@dataclass
class FailureImpact:
    failed: List[str]
    blocked: List[str]
    impacted: List[str]
    frozen: List[str]

    def to_dict(self):
        return {
            "failed": list(self.failed),
            "blocked": list(self.blocked),
            "impacted": list(self.impacted),
            "frozen": list(self.frozen),
        }


class FailureImpactAnalyzer:
    """Find failed nodes and every downstream node invalidated by them."""

    def analyze(self, plan: Plan, report: RunReport) -> FailureImpact:
        task_map = plan.task_map()
        failed = {
            task_id for task_id, result in report.results.items()
            if task_id in task_map and result.status != "success"
        }
        not_executed = set(task_map) - set(report.results)
        failed.update(task_id for task_id in not_executed if not task_map[task_id].depends_on)
        impacted = set(failed)
        changed = True
        while changed:
            changed = False
            for task in plan.subtasks:
                if task.id not in impacted and any(dep in impacted for dep in task.depends_on):
                    impacted.add(task.id)
                    changed = True
        blocked = not_executed & impacted
        frozen = {
            task_id for task_id, result in report.results.items()
            if task_id not in impacted and result.status == "success"
        }
        return FailureImpact(
            failed=sorted(failed),
            blocked=sorted(blocked),
            impacted=[task.id for task in plan.subtasks if task.id in impacted],
            frozen=[task.id for task in plan.subtasks if task.id in frozen],
        )


class AgentReplacementPolicy:
    """Conservatively change roles only when the task shape makes it safe."""

    def select(self, task: SubTask, result: AgentResult | None, available_roles: Set[str]) -> str:
        failures = " ".join(result.failures if result else []).lower()
        checks = task.metadata.get("checks", [])
        check_types = {item.get("check_type") for item in checks}
        expected_outputs = task.metadata.get("expected_outputs", [])
        exhausted = any(marker in failures for marker in ("max_tool_steps", "repeated_tool_call", "timeout"))
        if not exhausted:
            return task.role
        if task.role == "developer" and check_types and check_types <= {"command"} and "tester" in available_roles:
            return "tester"
        if task.role == "tester" and expected_outputs and "developer" in available_roles:
            return "developer"
        if task.role == "researcher" and "experimenter" in available_roles:
            return "experimenter"
        if task.role == "experimenter" and "researcher" in available_roles:
            return "researcher"
        return task.role


class RecoverySubgraphGenerator:
    """Rebuild only impacted tasks while treating successful predecessors as frozen."""

    def __init__(self, replacement_policy=None):
        self.replacement_policy = replacement_policy or AgentReplacementPolicy()

    def build(self, plan, report, impact, cycle, available_roles):
        task_map = plan.task_map()
        impacted = set(impact.impacted)
        tasks = []
        for task_id in impact.impacted:
            original = task_map[task_id]
            task = deepcopy(original)
            prior = report.results.get(task_id)
            task.depends_on = [dep for dep in original.depends_on if dep in impacted]
            task.role = self.replacement_policy.select(task, prior, available_roles)
            task.metadata["local_recovery_feedback"] = {
                "cycle": cycle,
                "original_role": original.role,
                "assigned_role": task.role,
                "prior_status": prior.status if prior else "blocked",
                "prior_failures": list(prior.failures) if prior else ["blocked by failed dependency"],
                "prior_summary": prior.summary if prior else "",
                "prior_artifacts": list(prior.artifacts) if prior else [],
                "prior_tool_results": [
                    {"tool": record.get("tool"), "success": record.get("success"),
                     "arguments": {key: value for key, value in record.get("arguments", {}).items() if key != "content"},
                     "output": str(record.get("output_excerpt", ""))[:500]}
                    for record in (prior.tool_records[-8:] if prior else [])
                ],
                "frozen_predecessors": [dep for dep in original.depends_on if dep in impact.frozen],
                "frozen_tasks": list(impact.frozen),
            }
            tasks.append(task)
        recovery = Plan(
            goal=f"Local recovery cycle {cycle}: {plan.goal}",
            subtasks=tasks,
            final_acceptance=list(plan.final_acceptance),
        )
        recovery.validate()
        return recovery


@dataclass
class LocalRecoveryOutcome:
    report: RunReport
    cycles: int = 0
    executed_tasks: int = 0
    impacts: List[Dict] = field(default_factory=list)


class LocalDAGRecoveryController:
    """Run bounded intra-phase recovery before escalating to a new phase."""

    def __init__(self, orchestrator, max_cycles=1, analyzer=None, generator=None, on_event=None):
        if max_cycles < 0:
            raise ValueError("max_cycles cannot be negative")
        self.orchestrator = orchestrator
        self.max_cycles = max_cycles
        self.analyzer = analyzer or FailureImpactAnalyzer()
        self.generator = generator or RecoverySubgraphGenerator()
        self.on_event = on_event

    def run(self, plan: Plan, task_budget: int, initial_results=None) -> LocalRecoveryOutcome:
        report = self.orchestrator.run(plan, initial_results=initial_results)
        executed = report.executed_task_count
        impacts = []
        attempted_cycles = 0
        for cycle in range(1, self.max_cycles + 1):
            if report.status == "success":
                break
            if any(
                "model_request_failed" in failure or "global " in failure and "budget" in failure
                for result in report.results.values() for failure in result.failures
            ):
                break  # resume this phase after the API/budget becomes available
            impact = self.analyzer.analyze(plan, report)
            impacts.append(impact.to_dict())
            if not impact.impacted:
                break
            if executed + len(impact.impacted) > task_budget:
                self._emit("local_recovery_budget_exhausted", {
                    "cycle": cycle, "needed": len(impact.impacted),
                    "remaining": max(0, task_budget - executed),
                })
                break
            attempted_cycles += 1
            self._emit("local_recovery_started", {"cycle": cycle, **impact.to_dict()})
            subgraph = self.generator.build(
                plan, report, impact, cycle, set(self.orchestrator.registry.roles())
            )
            self._emit("local_recovery_planned", {
                "cycle": cycle,
                "tasks": [
                    {"id": task.id, "role": task.role, "depends_on": list(task.depends_on)}
                    for task in subgraph.subtasks
                ],
            })
            frozen_results = {key: value for key, value in report.results.items() if key in impact.frozen}
            recovered = self.orchestrator.run(subgraph, context_results=frozen_results)
            executed += len(subgraph.subtasks)
            report = self._merge(plan, report, recovered, impact)
            self._emit("local_recovery_finished", {
                "cycle": cycle, "status": report.status,
                "recovered": [
                    task_id for task_id in impact.impacted
                    if task_id in report.results and report.results[task_id].status == "success"
                ],
                "remaining_failed": [
                    task_id for task_id in impact.impacted
                    if task_id not in report.results or report.results[task_id].status != "success"
                ],
            })
        report.executed_task_count = executed
        report.local_recovery_cycles = attempted_cycles
        return LocalRecoveryOutcome(report, attempted_cycles, executed, impacts)

    @staticmethod
    def _merge(plan, prior, recovered, impact):
        impacted = set(impact.impacted)
        results = {task_id: result for task_id, result in prior.results.items() if task_id not in impacted}
        for task_id, result in recovered.results.items():
            previous = prior.results.get(task_id)
            if previous:
                result.artifacts = list(dict.fromkeys(previous.artifacts + result.artifacts))
                result.evidence = list(dict.fromkeys(previous.evidence + result.evidence))
                result.tool_records = previous.tool_records + result.tool_records
        results.update(recovered.results)
        missing = [task.id for task in plan.subtasks if task.id not in results]
        failures = [
            f"{task_id}: {', '.join(result.failures) or result.status}"
            for task_id, result in results.items() if result.status != "success"
        ]
        failures.extend(f"{task_id}: blocked by failed dependency" for task_id in missing)
        return RunReport(
            goal=plan.goal,
            status="success" if not failures and len(results) == len(plan.subtasks) else "failed",
            results=results,
            rounds=prior.rounds + recovered.rounds,
            started_at=prior.started_at,
            finished_at=recovered.finished_at,
            failures=failures,
            started_epoch=prior.started_epoch,
            finished_epoch=recovered.finished_epoch,
        )

    def _emit(self, event, payload):
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass
