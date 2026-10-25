"""Offline two-phase demonstration of the LongHorizonController."""

import os
from datetime import datetime, timezone
from pathlib import Path

from core.agents import AgentRegistry, DeterministicAgent
from core.long_horizon import GoalEvaluation, LongHorizonController, LongHorizonStore
from core.models import Plan, SubTask
from core.orchestrator import Orchestrator


class DemoGlobalEvaluator:
    def evaluate(self, state, plan, report):
        if state.phase == 0:
            return GoalEvaluation(
                completed=False,
                reason="implementation phase passed; independent verification is still required",
                next_focus=["independent verification"],
                evidence=[f"implementation_status={report.status}"],
            )
        return GoalEvaluation(
            completed=report.status == "success",
            reason="implementation and independent verification both passed",
            evidence=[f"verification_status={report.status}"],
        )


def initial_plan(_state):
    return Plan(
        "phase 1: implement the requested change",
        [SubTask("implementation", "developer", "implement the requested change")],
    )


def replan(_state, evaluation):
    return Plan(
        "phase 2: verify the implementation",
        [
            SubTask("test", "tester", "run independent verification"),
            SubTask("review", "reviewer", "review the evidence", depends_on=["test"]),
        ],
    )


def build_controller():
    registry = AgentRegistry()
    for role in ("developer", "tester", "reviewer"):
        registry.register(DeterministicAgent(role))
    runs_root = Path(
        os.getenv("LONG_HORIZON_RUNS_DIR", str(Path(__file__).parent / "runs" / "long_horizon"))
    )
    store = LongHorizonStore(runs_root)
    return LongHorizonController(
        Orchestrator(registry, max_workers=2),
        initial_plan,
        store,
        evaluator=DemoGlobalEvaluator(),
        replanner=replan,
        max_phases=3,
        on_event=lambda event, payload: print(f"{event}: {payload}"),
    )


if __name__ == "__main__":
    run_id = "local-demo-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report = build_controller().run(
        "deliver and independently verify a software change",
        run_id=run_id,
        resume=False,
    )
    print(f"status={report.status} phases={report.state.phase} tasks={report.state.total_tasks}")
    print(f"run_id={report.state.run_id}")
