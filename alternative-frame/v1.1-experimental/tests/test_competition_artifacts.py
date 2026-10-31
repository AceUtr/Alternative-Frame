import json

from tools.build_competition_artifacts import main as build_main
from tools.verify_competition_manifest import main as verify_main


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_competition_package_uses_explicit_inputs_and_verifies_hashes(tmp_path, monkeypatch):
    sources = tmp_path / "source"
    agent = write_json(sources / "agents.json", {
        "evidence_kind": "deterministic_controlled_run", "repeats": 2,
        "summaries": [
            {"mode": "single_agent", "mean_duration_seconds": 0.4, "goal_completion_rate": 1},
            {"mode": "multi_agent", "mean_duration_seconds": 0.3, "goal_completion_rate": 1},
        ],
    })
    recovery = write_json(sources / "recovery.json", {
        "evidence_kind": "deterministic_controlled_run", "results": [
            {"mode": "recovery_off", "goal_completed": False},
            {"mode": "recovery_on", "goal_completed": True},
        ],
    })
    contract = write_json(sources / "contract.json", {
        "evidence_kind": "deterministic_controlled_run", "results": [
            {"mode": "contract_off", "completed": True},
            {"mode": "contract_on", "completed": False},
        ],
    })
    routing = write_json(sources / "routing.json", {
        "evidence_kind": "deterministic_controlled_run", "results": [
            {"mode": "fixed_cloud", "completed": False},
            {"mode": "dynamic_routing", "completed": True},
        ],
    })
    research = write_json(sources / "research.json", {
        "evidence_kind": "recorded_real_run", "runs": [
            {"case": "research_normal", "first_pass_count": 8, "local_recovery_count": 0},
            {"case": "research_local_recovery", "first_pass_count": 7, "local_recovery_count": 1},
        ],
    })
    output = tmp_path / "package"
    monkeypatch.setattr("sys.argv", [
        "build_competition_artifacts", "--output", str(output), "--commit", "abc123",
        "--agent", str(agent), "--recovery", str(recovery), "--contract", str(contract),
        "--routing", str(routing), "--research", str(research),
    ])
    assert build_main() == 0

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_commit"] == "abc123"
    assert manifest["live_api_status"] == "pending_credentials"
    assert len(manifest["sources"]) == 5
    assert len(manifest["charts"]) == 5

    monkeypatch.setattr("sys.argv", ["verify_competition_manifest", str(output / "manifest.json")])
    assert verify_main() == 0

    chart = output / manifest["charts"][0]["path"]
    chart.write_bytes(chart.read_bytes() + b"tampered")
    assert verify_main() == 1
