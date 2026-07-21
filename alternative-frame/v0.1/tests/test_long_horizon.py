import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.agents import AgentRegistry, DeterministicAgent
from core.long_horizon import GoalEvaluation, LongHorizonController, LongHorizonState, LongHorizonStore
from core.long_horizon.state import plan_to_dict
from core.models import Plan, SubTask
from core.orchestrator import Orchestrator


def make_orchestrator():
    registry = AgentRegistry()
    registry.register(DeterministicAgent("worker"))
    return Orchestrator(registry)


class CompleteOnSecondPhase:
    def evaluate(self, state, plan, report):
        if state.phase == 0:
            return GoalEvaluation(False, "implementation exists but verification is missing", next_focus=["verify"])
        return GoalEvaluation(True, "implementation and verification phases passed", evidence=["verified=true"])


def test_controller_replans_and_persists_two_phases(tmp_path):
    events = []

    def initial(_state):
        return Plan("implement", [SubTask("implement", "worker", "implement feature")])

    def replan(_state, evaluation):
        assert evaluation.next_focus == ["verify"]
        return Plan("verify", [SubTask("verify", "worker", "verify feature")])

    store = LongHorizonStore(tmp_path)
    controller = LongHorizonController(
        make_orchestrator(),
        initial,
        store,
        evaluator=CompleteOnSecondPhase(),
        replanner=replan,
        on_event=lambda event, payload: events.append(event),
    )

    report = controller.run("deliver a verified feature", run_id="two-phase")

    assert report.status == "completed"
    assert report.state.phase == 2
    assert report.state.total_tasks == 2
    assert len(report.state.phases) == 2
    assert report.state.pending_plan is None
    assert "run_completed" in events
    persisted = json.loads((tmp_path / "two-phase" / "state.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "completed"
    assert (tmp_path / "two-phase" / "events.jsonl").is_file()


def test_controller_stops_before_task_budget_is_exceeded(tmp_path):
    plan = Plan(
        "too large",
        [SubTask("one", "worker", "one"), SubTask("two", "worker", "two")],
    )
    controller = LongHorizonController(
        make_orchestrator(),
        lambda _state: plan,
        LongHorizonStore(tmp_path),
        max_total_tasks=1,
    )

    report = controller.run("bounded work", run_id="budget")

    assert report.status == "budget_exhausted"
    assert report.state.phase == 0
    assert report.state.last_error == "max_total_tasks_exceeded"


def test_controller_resumes_a_persisted_pending_phase(tmp_path):
    pending = Plan("resume phase", [SubTask("resume-task", "worker", "resume")])
    state = LongHorizonState("resume-run", "resume goal", max_phases=3, max_total_tasks=10)
    state.status = "running"
    state.pending_plan = plan_to_dict(pending)
    store = LongHorizonStore(tmp_path)
    store.save(state)

    def initial_should_not_run(_state):
        raise AssertionError("resume must use the persisted pending plan")

    controller = LongHorizonController(make_orchestrator(), initial_should_not_run, store)
    report = controller.run("resume goal", run_id="resume-run", resume=True)

    assert report.status == "completed"
    assert report.state.phase == 1
    assert report.state.completed_tasks == ["phase-1:resume-task"]
