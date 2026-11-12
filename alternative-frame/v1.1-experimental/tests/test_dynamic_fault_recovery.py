from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.edge_cloud.demo import run_experiment
from core.edge_cloud.evidence import verify_run
from core.edge_cloud.fault_injector import inject_process_failure
from core.long_horizon.dynamic_change_demo import run_experiment as run_change_experiment
from core.long_horizon.dynamic_change_demo import verify_run as verify_change_run


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("injection_delay", [0.5, 0.9, 1.3])
def test_external_process_failure_recovers_inside_main_long_horizon_controller(tmp_path, injection_delay):
    summary = run_experiment(
        tmp_path / "evidence",
        run_id=f"fault-recovery-test-{str(injection_delay).replace('.', '-')}",
        injection_delay_seconds=injection_delay,
        cloud_delay_seconds=5,
        cloud_timeout_seconds=3,
    )

    assert summary["verification_passed"] is True
    assert summary["network_scope"] == "single_host_loopback_control"
    assert summary["checks"]["cloud_was_processing_at_injection"] is True
    assert summary["checks"]["framework_observed_cloud_failure"] is True
    assert summary["checks"]["framework_failed_over_to_edge"] is True
    assert summary["checks"]["edge_completed_remote_task"] is True
    assert summary["checks"]["long_horizon_controller_completed"] is True
    assert summary["checks"]["required_artifact_exists"] is True
    assert summary["checks"]["artifact_records_edge_execution"] is True
    assert summary["checks"]["artifact_digest_matches_task_input"] is True

    run_dir = tmp_path / "evidence" / f"fault-recovery-test-{str(injection_delay).replace('.', '-')}"
    framework_events = read_jsonl(run_dir / summary["framework_events_path"])
    injector_events = read_jsonl(run_dir / summary["injector_events_path"])
    cloud_events = read_jsonl(run_dir / summary["cloud_worker_events_path"])
    assert [event["event"] for event in injector_events] == ["injector_armed", "fault_injection_triggered"]
    assert any(event["event"] == "remote_attempt_started" and event["payload"]["node_id"] == "cloud-01" for event in framework_events)
    assert any(event["event"] == "remote_failover" and event["payload"]["to_node"] == "edge-01" for event in framework_events)
    assert any(event["event"] == "worker_task_started" for event in cloud_events)
    assert not any(event["event"] == "worker_task_finished" for event in cloud_events)

    artifact = run_dir / summary["artifact_path"]
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == summary["artifact_sha256"]
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    for record in manifest["files"]:
        path = run_dir / record["path"]
        assert path.is_file()
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]

    verification = verify_run(run_dir)
    assert verification.passed is True
    assert verification.checks["injector_targeted_the_logged_worker"] is True
    assert verification.checks["cloud_and_edge_source_revisions_match"] is True
    strict_verification = verify_run(run_dir, require_edge_log=True, require_cross_host=True)
    assert strict_verification.passed is False
    assert any("cross-host claim" in failure for failure in strict_verification.failures)


def test_independent_verifier_rejects_tampered_edge_log(tmp_path):
    summary = run_experiment(
        tmp_path / "evidence",
        run_id="fault-recovery-tamper-test",
        injection_delay_seconds=0.7,
        cloud_delay_seconds=4,
        cloud_timeout_seconds=2.5,
    )
    run_dir = tmp_path / "evidence" / "fault-recovery-tamper-test"
    assert summary["verification_passed"] is True
    with (run_dir / "edge_worker_events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{}\n")

    verification = verify_run(run_dir)
    assert verification.passed is False
    assert verification.checks["manifest_hashes_valid"] is False


def test_external_requirement_change_replans_and_retains_baseline(tmp_path):
    summary = run_change_experiment(
        tmp_path / "changes",
        run_id="dynamic-change-test",
        injection_delay_seconds=0.05,
    )

    assert summary["verification_passed"] is True
    assert summary["phase_count"] == 2
    assert summary["checks"]["controller_replanned"] is True
    assert summary["checks"]["baseline_artifact_retained"] is True
    run_dir = tmp_path / "changes" / "dynamic-change-test"
    verification = verify_change_run(run_dir)
    assert verification["passed"] is True
    assert verification["checks"]["controller_planned_second_phase_without_repeating_baseline"] is True


def test_fault_injector_refuses_to_terminate_its_own_process(tmp_path):
    with pytest.raises(ValueError, match="different, non-system process"):
        inject_process_failure(os.getpid(), 0, tmp_path / "injector.jsonl", "test", "cloud-01")


def test_dynamic_fault_demo_preserves_existing_run_evidence(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    run_dir = evidence / "do-not-overwrite"
    run_dir.mkdir()
    existing = run_dir / "prior-evidence.txt"
    existing.write_text("prior evidence", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run_experiment(evidence, run_id="do-not-overwrite")

    assert existing.read_text(encoding="utf-8") == "prior evidence"
