import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.long_horizon import (
    GoalEvaluation,
    LongHorizonState,
    PlanValidationError,
    PlanValidator,
    StructuredReplanner,
    StructuredReplanError,
    LongHorizonController,
    LongHorizonStore,
)
from core.agents import AgentRegistry, DeterministicAgent
from core.models import Plan, SubTask
from core.orchestrator import Orchestrator


def valid_payload():
    return {
        "phase_goal": "diagnose, repair, and verify the failed service",
        "tasks": [
            {
                "id": "diagnose",
                "role": "developer",
                "description": "inspect the failed test and implementation",
                "depends_on": [],
                "required_tools": ["file_editor", "test_runner"],
                "expected_outputs": [],
                "checks": [{"id": "diagnosis_recorded", "check_type": "manual"}],
                "max_retries": 0,
            },
            {
                "id": "verify",
                "role": "tester",
                "description": "run the focused regression test",
                "depends_on": ["diagnose"],
                "required_tools": ["test_runner"],
                "expected_outputs": ["test-report.json"],
                "checks": [
                    {
                        "id": "focused_test_passes",
                        "check_type": "command",
                        "command": "python -m unittest -v test_service.py",
                    }
                ],
                "max_retries": 1,
            },
        ],
        "final_acceptance": ["focused_test_passes"],
    }


class SequenceClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.messages = []

    def chat(self, messages, tools=None):
        self.messages.append(messages)
        return {"content": json.dumps(self.payloads.pop(0))}


def make_state():
    return LongHorizonState(
        "run",
        "repair the software service",
        max_phases=3,
        max_total_tasks=10,
        phase=1,
        total_tasks=3,
        failed_tasks=["phase-1:integration"],
        artifacts=["src/service.py"],
    )


def test_structured_replanner_builds_a_valid_recovery_dag():
    events = []
    replanner = StructuredReplanner(
        SequenceClient([valid_payload()]),
        on_event=lambda event, payload: events.append(event),
    )

    plan = replanner(make_state(), GoalEvaluation(False, "integration test failed"))

    assert [task.id for task in plan.subtasks] == ["diagnose", "verify"]
    assert plan.subtasks[1].depends_on == ["diagnose"]
    assert plan.subtasks[1].metadata["required_tools"] == ["test_runner"]
    assert events == ["replan_started", "replan_completed"]


def test_structured_replanner_requests_one_correction_after_validation_failure():
    invalid = valid_payload()
    invalid["tasks"][0]["role"] = "root_admin"
    client = SequenceClient([invalid, valid_payload()])
    events = []
    replanner = StructuredReplanner(
        client,
        max_attempts=2,
        on_event=lambda event, payload: events.append(event),
    )

    plan = replanner(make_state(), GoalEvaluation(False, "integration test failed"))

    assert plan.subtasks[0].role == "developer"
    assert len(client.messages) == 2
    assert events == [
        "replan_started",
        "replan_validation_failed",
        "replan_started",
        "replan_completed",
    ]
    assert "unknown role" in client.messages[1][-1]["content"]


def test_plan_validator_rejects_tool_escalation_and_unsafe_outputs():
    task = SubTask(
        "review",
        "reviewer",
        "review files",
        metadata={
            "required_tools": ["shell_runner"],
            "expected_outputs": ["../outside.txt"],
            "checks": [{"id": "reviewed", "check_type": "manual"}],
        },
    )

    try:
        PlanValidator().validate(Plan("unsafe", [task]), remaining_task_budget=2)
    except PlanValidationError as exc:
        error = str(exc)
        assert "cannot use tools" in error
        assert "unsafe output path" in error
    else:
        raise AssertionError("unsafe dynamic plan should be rejected")


def test_plan_validator_rejects_cycles_and_budget_overflow():
    checks = [{"id": "done", "check_type": "manual"}]
    plan = Plan(
        "cycle",
        [
            SubTask("one", "analyst", "one", depends_on=["two"], metadata={"checks": checks}),
            SubTask("two", "analyst", "two", depends_on=["one"], metadata={"checks": checks}),
        ],
    )

    try:
        PlanValidator().validate(plan, remaining_task_budget=1)
    except PlanValidationError as exc:
        error = str(exc)
        assert "remaining budget" in error
        assert "Cycle detected" in error
    else:
        raise AssertionError("cyclic over-budget plan should be rejected")


def test_controller_executes_model_generated_multi_agent_recovery_plan(tmp_path):
    registry = AgentRegistry()

    def fail_initial(_task, _context):
        raise RuntimeError("initial implementation failed")

    registry.register(DeterministicAgent("worker", handler=fail_initial))
    registry.register(DeterministicAgent("developer"))
    registry.register(DeterministicAgent("tester"))
    client = SequenceClient([valid_payload()])
    replanner = StructuredReplanner(client)
    initial = lambda _state: Plan(
        "initial phase",
        [SubTask("initial", "worker", "fail once", max_retries=0)],
    )
    controller = LongHorizonController(
        Orchestrator(registry),
        initial,
        LongHorizonStore(tmp_path),
        replanner=replanner,
        max_phases=3,
    )

    report = controller.run("repair the software service", run_id="dynamic-recovery")

    assert report.status == "completed"
    assert report.state.phase == 2
    assert report.state.failed_tasks == ["phase-1:initial"]
    assert {item.task_ids[0] for item in report.state.phases} >= {"initial", "diagnose"}
    assert len(client.messages) == 1


def test_replanner_retries_transport_timeout_before_failing():
    class TimeoutClient:
        def __init__(self):
            self.calls = 0

        def chat(self, _messages, tools=None):
            self.calls += 1
            raise TimeoutError("read operation timed out")

    client = TimeoutClient()
    state = LongHorizonState("run", "goal", max_phases=3, max_total_tasks=10, phase=1)
    evaluation = GoalEvaluation(False, "missing", missing_criteria=["docs"])
    replanner = StructuredReplanner(client, max_attempts=2, retry_delays=())

    try:
        replanner(state, evaluation)
    except StructuredReplanError as exc:
        assert "timed out" in str(exc)
    else:
        raise AssertionError("transport timeout must not be treated as a plan")
    assert client.calls == 2
