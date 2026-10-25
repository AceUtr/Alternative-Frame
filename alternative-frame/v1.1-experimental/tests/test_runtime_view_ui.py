import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from ui import latest_runtime_view, load_runtime_view, validate_runtime_view


def sample_payload(run_id="sample-run"):
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "nodes": [
            {
                "node_id": "edge-1",
                "node_type": "edge",
                "online": True,
                "network_available": True,
                "capabilities": ["compute"],
                "estimated_latency_ms": 20,
                "estimated_cost": 0.2,
                "health": "healthy",
            }
        ],
        "route_events": [],
        "metrics": {
            "node_distribution": {"device": 0, "edge": 1, "cloud": 0, "unknown": 0},
            "node_duration_seconds": {"device": 0, "edge": 0.1, "cloud": 0, "unknown": 0},
            "node_failure_count": {"device": 0, "edge": 0, "cloud": 0, "unknown": 0},
            "fallback_count": 0,
            "execution_attempt_count": 1,
            "no_eligible_node_count": 0,
        },
    }


def test_runtime_view_loader_accepts_v1_contract(tmp_path):
    path = tmp_path / "runtime_view.json"
    path.write_text(json.dumps(sample_payload()), encoding="utf-8")

    payload = load_runtime_view(path)

    assert payload["run_id"] == "sample-run"
    assert payload["metrics"]["node_distribution"]["edge"] == 1


def test_runtime_view_loader_accepts_utf8_bom(tmp_path):
    path = tmp_path / "runtime_view.json"
    path.write_text(json.dumps(sample_payload()), encoding="utf-8-sig")

    payload = load_runtime_view(path)

    assert payload["run_id"] == "sample-run"


def test_runtime_view_validation_rejects_missing_metrics():
    payload = sample_payload()
    del payload["metrics"]["fallback_count"]

    with pytest.raises(ValueError, match="fallback_count"):
        validate_runtime_view(payload)


def test_latest_runtime_view_selects_newest_run(tmp_path):
    old = tmp_path / "runs" / "old" / "runtime_view.json"
    new = tmp_path / "runs" / "new" / "runtime_view.json"
    old.parent.mkdir(parents=True)
    new.parent.mkdir(parents=True)
    old.write_text(json.dumps(sample_payload("old")), encoding="utf-8")
    new.write_text(json.dumps(sample_payload("new")), encoding="utf-8")
    old.touch()
    new.touch()
    old_time = old.stat().st_mtime - 5
    import os
    os.utime(old, (old_time, old_time))

    assert latest_runtime_view(tmp_path) == new
