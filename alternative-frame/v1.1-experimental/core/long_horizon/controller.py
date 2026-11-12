from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import Event
from typing import Callable, List, Optional
from uuid import uuid4

from ..models import Plan, utc_now
from ..orchestrator import Orchestrator, RunReport
from ..local_recovery import LocalDAGRecoveryController
from .evaluator import GoalEvaluation, ReportStatusEvaluator
from .acceptance_contract import AcceptanceContract
from .runtime_changes import RuntimeChangeInbox
from .state import LongHorizonState, PhaseRecord, plan_from_dict, plan_to_dict
from .store import LongHorizonStore


InitialPlanner = Callable[[LongHorizonState], Plan]
Replanner = Callable[[LongHorizonState, GoalEvaluation], Optional[Plan]]


@dataclass
class LongHorizonReport:
    state: LongHorizonState
    phase_reports: List[RunReport] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.state.status


class LongHorizonController:
    """Bounded phase loop above the existing dependency-aware Orchestrator."""

    TERMINAL_STATUSES = {"completed", "budget_exhausted", "failed"}

    def __init__(
        self,
        orchestrator: Orchestrator,
        initial_planner: InitialPlanner,
        store: LongHorizonStore,
        evaluator=None,
        replanner: Replanner | None = None,
        max_phases: int = 3,
        max_total_tasks: int = 50,
        on_event: Callable[[str, dict], None] | None = None,
        acceptance_contract: Optional[dict] = None,
        local_recovery: LocalDAGRecoveryController | None = None,
        workspace_path: str | None = None,
        runtime_change_inbox: RuntimeChangeInbox | None = None,
    ):
        if max_phases < 1 or max_total_tasks < 1:
            raise ValueError("long-horizon budgets must be positive")
        self.orchestrator = orchestrator
        self.initial_planner = initial_planner
        self.store = store
        self.evaluator = evaluator or ReportStatusEvaluator()
        self.replanner = replanner
        self.max_phases = max_phases
        self.max_total_tasks = max_total_tasks
        self.on_event = on_event
        self.acceptance_contract = acceptance_contract
        self.local_recovery = local_recovery
        self.workspace_path = workspace_path
        self.runtime_change_inbox = runtime_change_inbox
        self._pause_requested = Event()
        self._current_run_id = ""
        self._active_phase = 0
        previous_event = getattr(orchestrator, "_long_horizon_original_on_event", orchestrator.on_event)
        orchestrator._long_horizon_original_on_event = previous_event

        def durable_orchestrator_event(event, task, result=None):
            if event in {"task_started", "task_finished", "task_retry_scheduled"} and self._current_run_id:
                payload = {
                    "phase": self._active_phase,
                    "task_id": task.id,
                    "role": task.role,
                    "attempt": task.metadata.get("runtime_attempt"),
                }
                if result is not None:
                    payload["result"] = asdict(result)
                    original = self._active_plan.task_map().get(task.id, task)
                    payload["task_fingerprint"] = LongHorizonStore.task_fingerprint(original)
                    payload["artifact_hashes"] = LongHorizonStore.artifact_hashes(result, self.workspace_path or ".")
                self.store.append_event(self._current_run_id, event, payload)
            if previous_event:
                previous_event(event, task, result)

        orchestrator.on_event = durable_orchestrator_event

    def request_pause(self) -> None:
        """Request a safe pause at the next phase boundary."""
        self._pause_requested.set()

    @property
    def pause_requested(self) -> bool:
        return self._pause_requested.is_set()

    def run(self, goal: str, run_id: str | None = None, resume: bool = False) -> LongHorizonReport:
        if not goal or not goal.strip():
            raise ValueError("goal cannot be empty")
        run_id = run_id or uuid4().hex[:12]
        self._current_run_id = run_id
        state = self._load_or_create(goal.strip(), run_id, resume)
        if self.runtime_change_inbox:
            if not callable(getattr(self.evaluator, "update_contract", None)):
                raise ValueError("runtime changes require a contract-aware evaluator with update_contract")
            self.runtime_change_inbox.open(state)
            self.evaluator.update_contract(AcceptanceContract.from_dict(state.acceptance_contract))
        phase_reports: List[RunReport] = []
        if resume:
            self._pause_requested.clear()

        if resume and state.status == "completed":
            audit = self._audit_completed_state(state)
            if audit.completed:
                self._persist(state, "completed_run_audit_passed", audit.to_dict())
                return LongHorizonReport(state, phase_reports)
            state.status = "paused"
            state.last_evaluation = audit.to_dict()
            state.last_error = "completed_run_failed_contract_reaudit"
            state.decisions.append(f"completion revoked: {audit.reason}")
            self._persist(state, "completed_run_audit_failed", audit.to_dict())

        state.status = "running"
        state.last_error = None
        self._persist(state, "run_started", {"resume": resume})
        if self.runtime_change_inbox:
            self._persist(state, "runtime_change_inbox_ready", {
                "pending_path": str(self.runtime_change_inbox.pending),
                "contract_revision": state.contract_revision,
                "boundary": "after_phase_execution_before_final_acceptance",
            })
        if state.phase >= state.max_phases:
            state.status = "budget_exhausted"
            state.last_error = "max_phases_exceeded"
            self._persist(state, "budget_exhausted", {"reason": state.last_error, "phase_limit": state.max_phases})
            return LongHorizonReport(state, phase_reports)

        try:
            while state.phase < state.max_phases:
                if self._pause_requested.is_set():
                    state.status = "paused"
                    self._persist(state, "run_paused", {"phase": state.phase, "boundary": "before_phase"})
                    break
                try:
                    plan = self._next_plan(state)
                except Exception as exc:
                    if state.phase > 0:
                        state.status = "paused"
                        state.last_error = f"replan_pending: {type(exc).__name__}: {exc}"
                        self._persist(state, "replan_pending", {"phase": state.phase, "reason": state.last_error})
                        break
                    raise
                if plan is None:
                    state.status = "failed"
                    state.last_error = "replanner_did_not_produce_a_plan"
                    self._persist(state, "run_failed", {"reason": state.last_error})
                    break

                resumed_results = self.store.successful_results(
                    state.run_id, state.phase + 1, plan, self.workspace_path or "."
                ) if resume and hasattr(self.store, "successful_results") else {}
                remaining_task_count = len(plan.subtasks) - len(resumed_results)
                if state.total_tasks + remaining_task_count > state.max_total_tasks:
                    state.status = "budget_exhausted"
                    state.last_error = "max_total_tasks_exceeded"
                    self._persist(state, "budget_exhausted", {
                        "reason": state.last_error,
                        "remaining_tasks": remaining_task_count,
                        "task_limit": state.max_total_tasks,
                    })
                    break

                phase_number = state.phase + 1
                self._active_phase = phase_number
                self._active_plan = plan
                state.pending_plan = plan_to_dict(plan)
                self._persist(state, "phase_resume_results", {"phase": phase_number, "reused_tasks": sorted(resumed_results)})
                self._persist(
                    state,
                    "phase_planned",
                    {
                        "phase": phase_number,
                        "plan_goal": plan.goal,
                        "tasks": [
                            {
                                "id": task.id,
                                "role": task.role,
                                "depends_on": list(task.depends_on),
                            }
                            for task in plan.subtasks
                        ],
                    },
                )

                if self.local_recovery:
                    remaining_budget = state.max_total_tasks - state.total_tasks
                    self.local_recovery.on_event = (
                        lambda event, payload: self._persist(state, event, payload)
                    )
                    report = self.local_recovery.run(
                        plan, remaining_budget, initial_results=resumed_results
                    ).report
                else:
                    report = self.orchestrator.run(plan, initial_results=resumed_results)
                phase_reports.append(report)
                interruption = self._interruption_reason(report)
                if interruption:
                    state.status = "budget_exhausted" if "budget" in interruption.lower() else "paused"
                    state.last_error = interruption
                    state.pending_plan = plan_to_dict(plan)
                    self._persist(state, "run_interrupted", {"phase": phase_number, "reason": interruption, "status": state.status})
                    break
                evaluation, phase_terminal = self._evaluate_and_commit_phase(
                    state, phase_number, plan, report
                )
                if phase_terminal:
                    break

                state.decisions.append(f"phase {phase_number}: continue - {evaluation.reason}")
                if self._pause_requested.is_set():
                    state.status = "paused"
                    self._persist(state, "run_paused", {"phase": state.phase, "boundary": "after_phase"})
                    break
                if state.phase >= state.max_phases:
                    state.status = "budget_exhausted"
                    state.last_error = "max_phases_exceeded"
                    self._persist(state, "budget_exhausted", {"reason": state.last_error})
                    break
        except Exception as exc:
            state.status = "failed"
            state.last_error = f"{type(exc).__name__}: {exc}"
            self._persist(state, "run_failed", {"reason": state.last_error})
            raise

        return LongHorizonReport(state, phase_reports)

    def _evaluate_and_commit_phase(self, state, phase_number, plan, report):
        """Evaluate outside the inbox lock, then atomically settle against its latest request."""
        while True:
            self._apply_runtime_changes(state)
            evaluation = self.evaluator.evaluate(state, plan, report)

            if self.runtime_change_inbox:
                with self.runtime_change_inbox.lock():
                    if self._apply_runtime_changes(state, lock_held=True):
                        continue
                    return self._commit_phase_evaluation(
                        state, phase_number, plan, report, evaluation
                    )
            return self._commit_phase_evaluation(state, phase_number, plan, report, evaluation)

    def _commit_phase_evaluation(self, state, phase_number, plan, report, evaluation):
        if evaluation.reason == "semantic global evaluation unavailable or invalid":
            state.status = "paused"
            state.last_error = "global_evaluation_pending"
            self._persist(state, "run_interrupted", {
                "phase": phase_number,
                "status": state.status,
                "reason": state.last_error,
            })
            return evaluation, True

        self._record_phase(state, phase_number, plan, report, evaluation)
        state.pending_plan = None
        state.last_evaluation = evaluation.to_dict()
        state.phase = phase_number
        self._persist(state, "phase_finished", {
            "phase": phase_number,
            "contract_revision": state.contract_revision,
            **evaluation.to_dict(),
        })

        if evaluation.completed:
            state.status = "completed"
            state.decisions.append(f"phase {phase_number}: final goal accepted - {evaluation.reason}")
            self._persist(state, "run_completed", {
                "phase": phase_number,
                "contract_revision": state.contract_revision,
            })
            return evaluation, True
        return evaluation, False

    def _apply_runtime_changes(self, state: LongHorizonState, *, lock_held: bool = False) -> bool:
        inbox = self.runtime_change_inbox
        if inbox is None:
            return False
        if not lock_held:
            with inbox.lock():
                return self._apply_runtime_changes(state, lock_held=True)
        changed = False
        for path in inbox.pending_paths():
            try:
                updated, record = inbox.prepare(path, state)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                rejected = inbox.reject(path, f"{type(exc).__name__}: {exc}")
                self._persist(state, "runtime_change_rejected", rejected)
                continue
            if updated is None:
                inbox.acknowledge(path, record["request_sha256"])
                self._persist(state, "runtime_change_duplicate_ignored", {
                    "request_id": record["request_id"],
                    "revision": record["revision"],
                })
                continue
            self.evaluator.update_contract(AcceptanceContract.from_dict(updated))
            state.acceptance_contract = updated
            self.acceptance_contract = updated
            state.contract_revision = record["revision"]
            state.runtime_changes.append(record)
            state.decisions.append(
                f"runtime change {record['request_id']} applied at contract revision {record['revision']}: {record['description']}"
            )
            self._persist(state, "runtime_change_applied", record)
            inbox.acknowledge(path, record["request_sha256"])
            changed = True
        return changed

    @staticmethod
    def _interruption_reason(report):
        for result in report.results.values():
            if result.status == "success":
                continue
            for failure in result.failures:
                if any(marker in failure.lower() for marker in (
                    "model_request_failed", "global token budget", "global model call budget",
                    "global run time budget", "provider usage exceeded", "api usage checkpoint failed",
                )):
                    return failure
        return None

    def _audit_completed_state(self, state: LongHorizonState) -> GoalEvaluation:
        """Re-check persisted completion against the current contract evaluator.

        This repairs historical runs that were marked complete by the legacy
        phase-status evaluator without contract evidence.
        """
        if not state.acceptance_contract or isinstance(self.evaluator, ReportStatusEvaluator):
            return GoalEvaluation(True, "no contract-aware completion audit is available")
        empty_plan = Plan(state.goal, [], final_acceptance=[])
        now = utc_now()
        audit_report = RunReport(state.goal, "success", {}, 0, now, now)
        return self.evaluator.evaluate(state, empty_plan, audit_report)

    def _load_or_create(self, goal: str, run_id: str, resume: bool) -> LongHorizonState:
        if resume:
            state = self.store.load(run_id)
            if state.goal != goal:
                raise ValueError("resume goal does not match persisted run goal")
            if self.acceptance_contract and state.acceptance_contract and state.acceptance_contract != self.acceptance_contract:
                raise ValueError("resume acceptance contract does not match persisted contract")
            if not state.acceptance_contract and self.acceptance_contract:
                state.acceptance_contract = self.acceptance_contract
            if state.max_phases < self.max_phases:
                state.max_phases = self.max_phases
                state.decisions.append(f"resume: expanded max_phases to {self.max_phases}")
            state.max_total_tasks = max(state.max_total_tasks, self.max_total_tasks)
            if state.workspace_path and self.workspace_path and state.workspace_path != self.workspace_path:
                raise ValueError("resume workspace does not match persisted run workspace")
            if not state.workspace_path and self.workspace_path:
                state.workspace_path = self.workspace_path
            return state
        if self.store.state_path(run_id).exists():
            raise FileExistsError(f"run already exists: {run_id}; use resume=True")
        return LongHorizonState(
            run_id=run_id,
            goal=goal,
            max_phases=self.max_phases,
            max_total_tasks=self.max_total_tasks,
            acceptance_contract=self.acceptance_contract,
            workspace_path=self.workspace_path,
        )

    def _next_plan(self, state: LongHorizonState) -> Plan | None:
        if state.pending_plan:
            return plan_from_dict(state.pending_plan)
        if state.phase == 0:
            return self.initial_planner(state)
        if not self.replanner or not state.last_evaluation:
            return None
        return self.replanner(state, GoalEvaluation.from_dict(state.last_evaluation))

    def _record_phase(
        self,
        state: LongHorizonState,
        phase_number: int,
        plan: Plan,
        report: RunReport,
        evaluation: GoalEvaluation,
    ) -> None:
        artifacts = [artifact for result in report.results.values() for artifact in result.artifacts]
        evidence_records = [record for result in report.results.values() for record in result.tool_records]
        completed = [f"phase-{phase_number}:{task_id}" for task_id, result in report.results.items() if result.status == "success"]
        failed = [f"phase-{phase_number}:{task_id}" for task_id, result in report.results.items() if result.status != "success"]
        state.total_tasks += report.executed_task_count
        state.completed_tasks.extend(completed)
        state.failed_tasks.extend(failed)
        for artifact in artifacts:
            if artifact not in state.artifacts:
                state.artifacts.append(artifact)
        state.evidence_records.extend(evidence_records)
        state.phases.append(
            PhaseRecord(
                number=phase_number,
                plan_goal=plan.goal,
                task_ids=[task.id for task in plan.subtasks],
                status="accepted" if evaluation.completed else "incomplete",
                report_status=report.status,
                evaluation=evaluation.to_dict(),
                failures=list(report.failures),
                artifacts=artifacts,
                started_at=report.started_at,
                finished_at=report.finished_at,
                local_recovery_cycles=report.local_recovery_cycles,
                executed_task_count=report.executed_task_count,
                contract_revision=state.contract_revision,
            )
        )

    def _persist(self, state: LongHorizonState, event: str, payload: dict) -> None:
        self.store.save(state)
        self.store.append_event(state.run_id, event, payload)
        if self.on_event:
            self.on_event(event, payload)
