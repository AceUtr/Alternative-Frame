from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event
from typing import Callable, List, Optional
from uuid import uuid4

from ..models import Plan
from ..orchestrator import Orchestrator, RunReport
from .evaluator import GoalEvaluation, ReportStatusEvaluator
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
        self._pause_requested = Event()

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
        state = self._load_or_create(goal.strip(), run_id, resume)
        phase_reports: List[RunReport] = []
        if resume:
            self._pause_requested.clear()

        if resume and state.status == "completed":
            return LongHorizonReport(state, phase_reports)

        state.status = "running"
        state.last_error = None
        self._persist(state, "run_started", {"resume": resume})

        try:
            while state.phase < state.max_phases:
                if self._pause_requested.is_set():
                    state.status = "paused"
                    self._persist(state, "run_paused", {"phase": state.phase, "boundary": "before_phase"})
                    break
                plan = self._next_plan(state)
                if plan is None:
                    state.status = "failed"
                    state.last_error = "replanner_did_not_produce_a_plan"
                    self._persist(state, "run_failed", {"reason": state.last_error})
                    break

                if state.total_tasks + len(plan.subtasks) > state.max_total_tasks:
                    state.status = "budget_exhausted"
                    state.last_error = "max_total_tasks_exceeded"
                    self._persist(state, "budget_exhausted", {"reason": state.last_error})
                    break

                phase_number = state.phase + 1
                state.pending_plan = plan_to_dict(plan)
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

                report = self.orchestrator.run(plan)
                phase_reports.append(report)
                evaluation = self.evaluator.evaluate(state, plan, report)
                self._record_phase(state, phase_number, plan, report, evaluation)
                state.pending_plan = None
                state.last_evaluation = evaluation.to_dict()
                state.phase = phase_number
                self._persist(state, "phase_finished", {"phase": phase_number, **evaluation.to_dict()})

                if evaluation.completed:
                    state.status = "completed"
                    state.decisions.append(f"phase {phase_number}: final goal accepted - {evaluation.reason}")
                    self._persist(state, "run_completed", {"phase": phase_number})
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

    def _load_or_create(self, goal: str, run_id: str, resume: bool) -> LongHorizonState:
        if resume:
            state = self.store.load(run_id)
            if state.goal != goal:
                raise ValueError("resume goal does not match persisted run goal")
            if self.acceptance_contract and state.acceptance_contract and state.acceptance_contract != self.acceptance_contract:
                raise ValueError("resume acceptance contract does not match persisted contract")
            if not state.acceptance_contract and self.acceptance_contract:
                state.acceptance_contract = self.acceptance_contract
            return state
        if self.store.state_path(run_id).exists():
            raise FileExistsError(f"run already exists: {run_id}; use resume=True")
        return LongHorizonState(
            run_id=run_id,
            goal=goal,
            max_phases=self.max_phases,
            max_total_tasks=self.max_total_tasks,
            acceptance_contract=self.acceptance_contract,
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
        state.total_tasks += len(plan.subtasks)
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
            )
        )

    def _persist(self, state: LongHorizonState, event: str, payload: dict) -> None:
        self.store.save(state)
        self.store.append_event(state.run_id, event, payload)
        if self.on_event:
            self.on_event(event, payload)
