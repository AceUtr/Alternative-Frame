import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.agents import Agent, AgentRegistry
from core.local_recovery import FailureImpactAnalyzer, LocalDAGRecoveryController
from core.long_horizon import LongHorizonController
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator


class RecoveringAgent(Agent):
    role = "worker"

    def __init__(self):
        self.calls = Counter()
        self.feedback = {}

    def run(self, task, context):
        self.calls[task.id] += 1
        self.feedback[task.id] = task.metadata.get("local_recovery_feedback")
        if task.id == "fragile" and self.calls[task.id] == 1:
            return AgentResult(task.id, "failed", failures=["temporary implementation failure"])
        return AgentResult(task.id, "success", summary=f"{task.id} complete")


def branching_plan():
    return Plan(
        "deliver branching workflow",
        [
            SubTask("stable", "worker", "independent successful work", max_retries=0),
            SubTask("fragile", "worker", "fails once", max_retries=0),
            SubTask("verify", "worker", "depends on repair", depends_on=["fragile"], max_retries=0),
        ],
    )


def test_failure_impact_freezes_success_and_selects_failed_descendants():
    registry = AgentRegistry()
    agent = RecoveringAgent()
    registry.register(agent)
    plan = branching_plan()
    report = Orchestrator(registry).run(plan)

    impact = FailureImpactAnalyzer().analyze(plan, report)

    assert impact.failed == ["fragile"]
    assert impact.blocked == ["verify"]
    assert impact.impacted == ["fragile", "verify"]
    assert impact.frozen == ["stable"]


def test_local_recovery_reruns_only_impacted_subgraph():
    registry = AgentRegistry()
    agent = RecoveringAgent()
    registry.register(agent)
    events = []
    recovery = LocalDAGRecoveryController(
        Orchestrator(registry),
        max_cycles=1,
        on_event=lambda event, payload: events.append((event, payload)),
    )

    outcome = recovery.run(branching_plan(), task_budget=10)

    assert outcome.report.status == "success"
    assert outcome.executed_tasks == 5
    assert agent.calls == Counter({"fragile": 2, "stable": 1, "verify": 1})
    assert agent.feedback["fragile"]["cycle"] == 1
    assert agent.feedback["verify"]["prior_status"] == "blocked"
    assert [event for event, _ in events] == [
        "local_recovery_started", "local_recovery_planned", "local_recovery_finished"
    ]


class MemoryStore:
    def __init__(self):
        self.states = {}

    def save(self, state):
        self.states[state.run_id] = state

    def append_event(self, run_id, event, payload=None):
        pass

    def state_path(self, run_id):
        class MissingPath:
            @staticmethod
            def exists():
                return False
        return MissingPath()


def test_long_horizon_local_recovery_completes_without_new_phase():
    registry = AgentRegistry()
    agent = RecoveringAgent()
    registry.register(agent)
    orchestrator = Orchestrator(registry)
    controller = LongHorizonController(
        orchestrator,
        lambda _state: branching_plan(),
        MemoryStore(),
        local_recovery=LocalDAGRecoveryController(orchestrator, max_cycles=1),
        max_phases=3,
        max_total_tasks=10,
    )

    report = controller.run("deliver branching workflow", run_id="local-recovery")

    assert report.status == "completed"
    assert report.state.phase == 1
    assert report.state.total_tasks == 5
    assert report.phase_reports[0].local_recovery_cycles == 1


def test_local_recovery_respects_total_task_budget():
    registry = AgentRegistry()
    agent = RecoveringAgent()
    registry.register(agent)
    events = []
    recovery = LocalDAGRecoveryController(
        Orchestrator(registry),
        max_cycles=1,
        on_event=lambda event, payload: events.append(event),
    )

    outcome = recovery.run(branching_plan(), task_budget=4)

    assert outcome.report.status == "failed"
    assert outcome.executed_tasks == 3
    assert "local_recovery_budget_exhausted" in events
