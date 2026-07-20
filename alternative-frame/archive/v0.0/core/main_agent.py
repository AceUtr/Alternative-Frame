from __future__ import annotations

from typing import Callable, Optional

from .models import Plan
from .planning import PlanningPipeline
from .orchestrator import Orchestrator, RunReport


class MainAgent:
    """The v0 coordinator facade: plan, delegate, summarize, optionally replan."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        planner: Callable[[str], Plan] | None = None,
        replanner: Optional[Callable[[str, RunReport], Plan]] = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.planner = planner or PlanningPipeline().build
        self.replanner = replanner

    def execute(self, goal: str, max_rounds: int = 2) -> RunReport:
        plan = self.planner(goal)
        report = self.orchestrator.run(plan)
        round_no = 1
        while report.status != "success" and self.replanner and round_no < max_rounds:
            round_no += 1
            plan = self.replanner(goal, report)
            report = self.orchestrator.run(plan)
        return report
