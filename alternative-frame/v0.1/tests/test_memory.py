from core.memory import ThreeLayerMemory, replay_events


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
