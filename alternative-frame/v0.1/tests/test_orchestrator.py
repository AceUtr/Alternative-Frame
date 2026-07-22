import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.agents import Agent, AgentRegistry, DeterministicAgent
from core.acceptance import AcceptanceEvaluator
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator


def test_parallel_dependencies_complete_in_rounds():
    registry = AgentRegistry()
    for role in ["a", "b", "c"]:
        registry.register(DeterministicAgent(role))
    plan = Plan("demo", [
        SubTask("a", "a", "first"),
        SubTask("b", "b", "parallel"),
        SubTask("c", "c", "join", depends_on=["a", "b"]),
    ])
    report = Orchestrator(registry, max_workers=2).run(plan)
    assert report.status == "success"
    assert report.rounds == 2
    assert all(item.status == "success" for item in report.results.values())


def test_cycle_is_rejected():
    plan = Plan("bad", [SubTask("a", "a", "a", depends_on=["b"]), SubTask("b", "b", "b", depends_on=["a"])])
    try:
        plan.validate()
    except ValueError as exc:
        assert "Cycle" in str(exc)
    else:
        raise AssertionError("cycle should be rejected")


class FeedbackRepairAgent(Agent):
    role = "writer"

    def __init__(self, workspace):
        self.workspace = workspace
        self.received = []

    def run(self, task, _context):
        feedback = task.metadata.get("retry_feedback")
        self.received.append(feedback)
        if feedback:
            path = self.workspace / "requirements.md"
            path.write_text("# Requirements\n", encoding="utf-8")
            return AgentResult(
                task.id,
                "success",
                summary="created missing artifact",
                artifacts=["requirements.md"],
                tool_records=[
                    {
                        "tool": "file_editor",
                        "success": True,
                        "metadata": {"artifacts": ["requirements.md"]},
                    }
                ],
            )
        return AgentResult(task.id, "success", summary="requirements described in prose only")


def test_acceptance_failure_is_fed_back_and_repaired_within_task(tmp_path):
    agent = FeedbackRepairAgent(tmp_path)
    registry = AgentRegistry()
    registry.register(agent)
    events = []
    task = SubTask(
        "requirements",
        "writer",
        "write requirements",
        max_retries=2,
        metadata={
            "expected_outputs": ["requirements.md"],
            "checks": [{"id": "requirements_written", "check_type": "file_exists"}],
        },
    )

    report = Orchestrator(
        registry,
        acceptance=AcceptanceEvaluator(tmp_path),
        on_event=lambda event, task, result=None: events.append((event, task, result)),
    ).run(Plan("write requirements", [task]))

    assert report.status == "success"
    assert report.results["requirements"].attempts == 2
    assert agent.received[0] is None
    assert agent.received[1]["category"] == "missing_artifact"
    assert "missing_artifacts=['requirements.md']" in agent.received[1]["failures"][0]
    assert any(event == "task_retry_scheduled" for event, _, _ in events)


class AlwaysMissingAgent(Agent):
    role = "writer"

    def run(self, task, _context):
        return AgentResult(task.id, "success", summary="prose only")


def test_feedback_retry_respects_task_budget(tmp_path):
    registry = AgentRegistry()
    registry.register(AlwaysMissingAgent())
    task = SubTask(
        "requirements",
        "writer",
        "write requirements",
        max_retries=1,
        metadata={
            "expected_outputs": ["requirements.md"],
            "checks": [{"id": "requirements_written", "check_type": "file_exists"}],
        },
    )

    report = Orchestrator(registry, acceptance=AcceptanceEvaluator(tmp_path)).run(Plan("goal", [task]))

    assert report.status == "failed"
    assert report.results["requirements"].attempts == 2
