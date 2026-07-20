import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.agents import AgentRegistry, DeterministicAgent
from core.models import Plan, SubTask
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

