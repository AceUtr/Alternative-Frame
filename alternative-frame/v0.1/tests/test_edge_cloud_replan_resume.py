import json

from core.runtime_nodes import CloudNode, EdgeNode, NodeStateStore
from run_edge_cloud_replan_demo import run_demo


def test_node_state_store_restores_dynamic_health(tmp_path):
    path = tmp_path / "node_state.json"
    original = [CloudNode("cloud-1", {"compute"}), EdgeNode("edge-1", {"compute"})]
    original[0].online = False
    original[0].network_available = False
    NodeStateStore(path).save(original)

    restored = NodeStateStore(path).restore(
        [CloudNode("cloud-1", {"compute"}), EdgeNode("edge-1", {"compute"})]
    )

    assert restored[0].online is False
    assert restored[0].network_available is False
    assert restored[1].online is True


def test_replanned_tasks_route_before_and_after_pause_resume(tmp_path):
    paused, completed, view, run_dir = run_demo(tmp_path, "replan-resume")

    assert paused.status == "paused"
    assert completed.status == "completed"
    records = [
        row for row in completed.state.evidence_records if row.get("tool") == "runtime_executor"
    ]
    successful = [(row["task_id"], row["node_type"]) for row in records if row["success"]]
    assert successful == [
        ("phase1_device_preprocess", "device"),
        ("phase2_cloud_recovery", "edge"),
        ("phase3_post_resume", "edge"),
    ]
    phase_two = [row for row in records if row["task_id"] == "phase2_cloud_recovery"]
    assert [row["node_type"] for row in phase_two] == ["cloud", "edge"]
    phase_three = [row for row in records if row["task_id"] == "phase3_post_resume"]
    assert len(phase_three) == 1
    assert phase_three[0]["fallback_count"] == 0
    assert view["nodes"][0]["node_id"] == "cloud-1"
    assert view["nodes"][0]["health"] == "offline"

    state_payload = json.loads((run_dir / "node_state.json").read_text(encoding="utf-8"))
    cloud = next(row for row in state_payload["nodes"] if row["node_id"] == "cloud-1")
    assert cloud["online"] is False
