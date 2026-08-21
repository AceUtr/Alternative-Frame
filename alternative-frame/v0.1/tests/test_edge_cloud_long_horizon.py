import json

from run_edge_cloud_long_horizon_demo import run_demo


def test_research_long_horizon_demo_routes_and_persists_runtime_data(tmp_path):
    demo = run_demo(tmp_path, "research-test")

    assert demo.report.status == "completed"
    events = [
        json.loads(line)
        for line in (demo.run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_names = {event["event"] for event in events}
    assert {
        "placement_decided",
        "node_execution_started",
        "node_execution_failed",
        "node_fallback_started",
        "node_execution_completed",
    } <= event_names

    runtime_records = [
        record
        for record in demo.report.state.evidence_records
        if record.get("tool") == "runtime_executor"
    ]
    assert [(row["task_id"], row["node_type"]) for row in runtime_records if row["success"]] == [
        ("preprocess_sensitive", "device"),
        ("edge_inference", "edge"),
        ("cloud_experiment", "cloud"),
        ("cloud_fault_recovery", "edge"),
    ]
    assert [row["node_type"] for row in runtime_records if row["task_id"] == "cloud_fault_recovery"] == [
        "cloud",
        "edge",
    ]
    for record in runtime_records:
        for field in ("node_id", "node_type", "placement_reason", "duration", "fallback_count"):
            assert field in record

    view = json.loads((demo.run_dir / "runtime_view.json").read_text(encoding="utf-8"))
    assert view["schema_version"] == "1.0"
    assert len(view["nodes"]) == 3
    assert view["metrics"]["node_distribution"] == {
        "device": 1,
        "edge": 2,
        "cloud": 1,
        "unknown": 0,
    }
    assert view["metrics"]["node_failure_count"]["cloud"] == 1
    assert view["metrics"]["fallback_count"] == 1
