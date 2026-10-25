from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from ..models import Plan
from ..orchestrator import RunReport
from .state import LongHorizonState


@dataclass
class GoalEvaluation:
    completed: bool
    reason: str
    satisfied_criteria: List[str] = field(default_factory=list)
    missing_criteria: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    next_focus: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoalEvaluation":
        return cls(**data)


class ReportStatusEvaluator:
    """Default evaluator: a fully successful phase satisfies the current goal."""

    def evaluate(self, state: LongHorizonState, plan: Plan, report: RunReport) -> GoalEvaluation:
        completed = report.status == "success" and len(report.results) == len(plan.subtasks)
        failures = list(report.failures)
        if completed:
            return GoalEvaluation(
                completed=True,
                reason="all phase tasks and their acceptance checks passed",
                evidence=[f"phase_tasks_passed={len(report.results)}"],
            )
        return GoalEvaluation(
            completed=False,
            reason="phase execution or acceptance failed",
            failures=failures or ["phase_incomplete"],
            next_focus=["analyze failed tasks and produce a revised phase plan"],
            evidence=[f"phase_report_status={report.status}"],
        )
