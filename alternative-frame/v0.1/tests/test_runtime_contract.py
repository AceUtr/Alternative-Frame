import json
from pathlib import Path

from core.runtime_nodes import aggregate_runtime_metrics


EXAMPLES = Path(__file__).parents[1] / "examples" / "edge_cloud"
METRIC_FIELDS = {
    "schema_version",
    "node_distribution",
    "node_duration_seconds",
    "node_failure_count",
    "fallback_count",
    "execution_attempt_count",
    "no_eligible_node_count",
}


def _load(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def test_fixed_runtime_view_samples_follow_v1_contract():
    for name in ("runtime_view_normal.json", "runtime_view_cloud_edge_fallback.json"):
        payload = _load(name)
        assert payload["schema_version"] == "1.0"
        assert payload["run_id"]
        assert isinstance(payload["nodes"], list)
        assert isinstance(payload["route_events"], list)
        assert set(payload["metrics"]) == METRIC_FIELDS
        for field in ("node_distribution", "node_duration_seconds", "node_failure_count"):
            assert set(payload["metrics"][field]) == {"device", "edge", "cloud", "unknown"}


def test_d_can_recompute_normal_sample_metrics_from_raw_records():
    records = _load("runtime_records_normal.json")
    expected = _load("runtime_view_normal.json")["metrics"]

    assert aggregate_runtime_metrics(records) == expected


def test_d_can_recompute_fallback_sample_metrics_from_raw_records():
    records = _load("runtime_records_cloud_edge_fallback.json")
    expected = _load("runtime_view_cloud_edge_fallback.json")["metrics"]

    assert aggregate_runtime_metrics(records) == expected


def test_missing_node_type_is_counted_as_unknown_not_device():
    metrics = aggregate_runtime_metrics(
        [{"tool": "runtime_executor", "task_id": "legacy", "success": True, "duration": 0.5}]
    )

    assert metrics["node_distribution"]["unknown"] == 1
    assert metrics["node_distribution"]["device"] == 0


def test_fixed_sample_triplets_share_run_id_and_recompute_metrics():
    for sample_name in ("normal", "cloud_edge_fallback"):
        sample = EXAMPLES / "samples" / sample_name
        state = json.loads((sample / "state.json").read_text(encoding="utf-8"))
        view = json.loads((sample / "runtime_view.json").read_text(encoding="utf-8"))
        events = [
            json.loads(line)
            for line in (sample / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]

        assert state["run_id"] == view["run_id"]
        assert all("event" in row and "payload" in row for row in events)
        assert aggregate_runtime_metrics(state["evidence_records"]) == view["metrics"]
