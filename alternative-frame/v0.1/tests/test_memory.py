from core.memory import ThreeLayerMemory, replay_events
from core.agents import AgentRegistry, DeterministicAgent
from core.long_horizon import DeterministicGlobalEvaluator, LongHorizonController, LongHorizonStore
from core.models import Plan, SubTask


def test_three_layer_memory_promote_persist_load(tmp_path):
    memory = ThreeLayerMemory(tmp_path)
    memory.remember("goal", "ship", tags=["contract"])
    memory.remember("phase-1", {"status": "failed"}, layer="episodic", phase=1)
    memory.promote("goal")
    loaded = ThreeLayerMemory.load(memory.persist())
    assert loaded.durable["goal"].value == "ship"
    assert loaded.episodic[0].phase == 1


def test_replay_events_is_ordered(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text('{"event":"a"}\n{"event":"b"}\n', encoding="utf-8")
    assert [item["event"] for item in replay_events(path)] == ["a", "b"]


def test_long_horizon_controller_persists_three_memory_layers(tmp_path):
    registry = AgentRegistry()
    registry.register(DeterministicAgent("developer"))
    plan = Plan("memory goal", [SubTask("implement", "developer", "implement")])
    controller = LongHorizonController(
        orchestrator=__import__("core.orchestrator", fromlist=["Orchestrator"]).Orchestrator(registry),
        initial_planner=lambda _state: plan,
        store=LongHorizonStore(tmp_path),
    )
    report = controller.run("memory goal", run_id="memory-run")
    memory = ThreeLayerMemory.load(tmp_path / "memory-run" / "memory.json")
    assert report.status == "completed"
    assert memory.working["goal"].value == "memory goal"
    assert any(item.key == "phase-1-plan" for item in memory.episodic)
    assert "final_evaluation" in memory.durable
