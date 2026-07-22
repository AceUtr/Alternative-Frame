from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from ..models import Plan, SubTask, utc_now


def plan_to_dict(plan: Plan) -> Dict[str, Any]:
    return asdict(plan)


def plan_from_dict(data: Dict[str, Any]) -> Plan:
    plan = Plan(
        goal=data["goal"],
        subtasks=[SubTask(**task) for task in data.get("subtasks", [])],
        final_acceptance=list(data.get("final_acceptance", [])),
    )
    plan.validate()
    return plan


@dataclass
class PhaseRecord:
    number: int
    plan_goal: str
    task_ids: List[str]
    status: str
    report_status: str
    evaluation: Dict[str, Any]
    failures: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""


@dataclass
class LongHorizonState:
    run_id: str
    goal: str
    max_phases: int
    max_total_tasks: int
    status: str = "pending"
    phase: int = 0
    total_tasks: int = 0
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    evidence_records: List[Dict[str, Any]] = field(default_factory=list)
    acceptance_contract: Dict[str, Any] | None = None
    decisions: List[str] = field(default_factory=list)
    phases: List[PhaseRecord] = field(default_factory=list)
    pending_plan: Dict[str, Any] | None = None
    last_evaluation: Dict[str, Any] | None = None
    last_error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LongHorizonState":
        values = dict(data)
        values["phases"] = [PhaseRecord(**phase) for phase in values.get("phases", [])]
        return cls(**values)

    def touch(self) -> None:
        self.updated_at = utc_now()
