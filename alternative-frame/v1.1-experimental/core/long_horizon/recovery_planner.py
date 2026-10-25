from __future__ import annotations

from typing import Callable, Optional

from .acceptance_contract import AcceptanceContract, GoalCriterion
from .evaluator import GoalEvaluation
from .initial_planner import RuleBasedContractPlanner
from .state import LongHorizonState


class DeterministicRecoveryPlanner:
    """Create a minimal safe recovery DAG from the missing contract criteria."""

    def __init__(self, planner=None):
        self.planner = planner or RuleBasedContractPlanner()

    def __call__(self, state: LongHorizonState, evaluation: GoalEvaluation):
        if not state.acceptance_contract:
            raise ValueError("cannot recover without a persisted acceptance contract")
        contract = AcceptanceContract.from_dict(state.acceptance_contract)
        missing = set(evaluation.missing_criteria)
        criteria = [item for item in contract.criteria if item.id in missing]
        if not criteria:
            criteria = [
                GoalCriterion(
                    id="semantic_goal_coverage",
                    description="Resolve the remaining semantic goal-coverage gap with concrete evidence.",
                    check_type="semantic",
                )
            ]
        recovery = AcceptanceContract(
            goal=state.goal,
            goal_summary=f"Recover {len(criteria)} missing acceptance criteria",
            criteria=criteria,
            constraints=list(contract.constraints),
        )
        return self.planner.build(recovery, task_budget=state.max_total_tasks - state.total_tasks)


class ResilientReplanner:
    """Use the model replanner first and deterministic recovery when it is unavailable."""

    def __init__(
        self,
        primary,
        fallback=None,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        self.primary = primary
        self.fallback = fallback or DeterministicRecoveryPlanner()
        self.on_event = on_event

    def __call__(self, state, evaluation):
        try:
            return self.primary(state, evaluation)
        except Exception as exc:
            self._emit("replan_fallback_started", {"error": f"{type(exc).__name__}: {exc}"})
            plan = self.fallback(state, evaluation)
            self._emit("replan_fallback_completed", {"task_count": len(plan.subtasks)})
            return plan

    def _emit(self, event, payload):
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass
