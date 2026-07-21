from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..models import Plan


@dataclass
class GoalCriterion:
    id: str
    description: str
    check_type: str
    required: bool = True
    path: Optional[str] = None
    command: Optional[str] = None
    metric_name: Optional[str] = None
    threshold: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AcceptanceContract:
    goal: str
    criteria: List[GoalCriterion] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"goal": self.goal, "criteria": [criterion.to_dict() for criterion in self.criteria]}

    @classmethod
    def from_plan(cls, goal: str, plan: Plan) -> "AcceptanceContract":
        criteria: List[GoalCriterion] = []
        for task in plan.subtasks:
            outputs = list(task.metadata.get("expected_outputs", []))
            for check in task.metadata.get("checks", []):
                check_id = str(check.get("id", f"{task.id}_check"))
                check_type = str(check.get("check_type", "manual"))
                description = str(check.get("description") or f"{task.id}: {check_id}")
                if check_type == "file_exists":
                    if outputs:
                        for index, output in enumerate(outputs, start=1):
                            criteria.append(
                                GoalCriterion(
                                    id=f"{task.id}:{check_id}:{index}",
                                    description=description,
                                    check_type=check_type,
                                    path=str(output),
                                )
                            )
                    else:
                        criteria.append(
                            GoalCriterion(
                                id=f"{task.id}:{check_id}",
                                description=description,
                                check_type=check_type,
                            )
                        )
                else:
                    criteria.append(
                        GoalCriterion(
                            id=f"{task.id}:{check_id}",
                            description=description,
                            check_type=check_type,
                            command=check.get("command"),
                            metric_name=check.get("metric_name"),
                            threshold=check.get("threshold"),
                        )
                    )
        return cls(goal=goal, criteria=criteria)
