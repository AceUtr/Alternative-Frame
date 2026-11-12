from __future__ import annotations

"""Independent verification for the dynamic edge/cloud fault experiment.

The verifier intentionally does not trust ``summary.json``. It reconstructs the
claim from the injector, framework, worker and artifact records, then checks the
manifest hashes separately.
"""

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Verification:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": self.checks,
            "failures": self.failures,
            "warnings": self.warnings,
            "details": self.details,
        }


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            value["_line"] = line_number
            records.append(value)
    return records


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    return value if isinstance(value, dict) else record


def verify_run(
    run_dir: str | Path,
    *,
    require_cross_host: bool = False,
    require_edge_log: bool = False,
    register_edge_log: bool = False,
) -> Verification:
    root = Path(run_dir).resolve()
    checks: dict[str, bool] = {}
    failures: list[str] = []
    warnings: list[str] = []

    def check(name: str, condition: bool, failure: str) -> None:
        checks[name] = bool(condition)
        if not condition:
            failures.append(failure)

    summary = _read_json(root / "summary.json")
    manifest = _read_json(root / "manifest.json")
    injector = _read_jsonl(root / "injector_events.jsonl")
    framework = _read_jsonl(root / "framework_runs" / (summary or {}).get("run_id", "") / "events.jsonl")
    state = _read_json(root / "framework_runs" / (summary or {}).get("run_id", "") / "state.json")
    cloud = _read_jsonl(root / "cloud_worker_events.jsonl")
    edge = _read_jsonl(root / "edge_worker_events.jsonl")

    run_id = (summary or {}).get("run_id")
    check("summary_exists_and_has_run_id", isinstance(summary, dict) and bool(run_id), "summary.json is missing a run_id")
    check("manifest_exists", isinstance(manifest, dict), "manifest.json is missing or invalid")
    if not run_id:
        run_id = ""

    def same_run(record: dict[str, Any]) -> bool:
        value = record.get("run_id")
        if value is None:
            value = _payload(record).get("run_id")
        # Framework lifecycle events are already isolated in this run's own
        # event file and do not repeat run_id in every record.
        return value == run_id if value is not None else True

    triggered = next((item for item in injector if item.get("event") == "fault_injection_triggered" and same_run(item)), None)
    armed = next((item for item in injector if item.get("event") == "injector_armed" and same_run(item)), None)
    cloud_started = next((item for item in cloud if item.get("event") == "worker_task_started" and same_run(item)), None)
    cloud_finished = next((item for item in cloud if item.get("event") == "worker_task_finished" and same_run(item)), None)
    cloud_attempt = next((
        item for item in framework
        if item.get("event") == "remote_attempt_started"
        and same_run(item)
        and _payload(item).get("node_id") == "cloud-01"
    ), None)
    cloud_failed = next((
        item for item in framework
        if item.get("event") == "remote_attempt_failed"
        and same_run(item)
        and _payload(item).get("node_id") == "cloud-01"
    ), None)
    failover = next((
        item for item in framework
        if item.get("event") == "remote_failover"
        and same_run(item)
        and _payload(item).get("from_node") == "cloud-01"
        and _payload(item).get("to_node") == "edge-01"
    ), None)
    edge_finished = next((
        item for item in framework
        if item.get("event") == "remote_task_completed"
        and same_run(item)
        and _payload(item).get("node_id") == "edge-01"
    ), None)
    edge_worker_started = next((item for item in edge if item.get("event") == "worker_task_started" and same_run(item)), None)
    edge_worker_finished = next((item for item in edge if item.get("event") == "worker_task_finished" and same_run(item)), None)
    cloud_process_started = next((item for item in cloud if item.get("event") == "worker_started"), None)

    target_task_id = (triggered or {}).get("target_task_id")
    cloud_task_id = _payload(cloud_started).get("task_id") if cloud_started else None
    failed_task_id = _payload(cloud_failed).get("task_id") if cloud_failed else None
    failover_task_id = _payload(failover).get("task_id") if failover else None
    edge_task_id = _payload(edge_finished).get("task_id") if edge_finished else None

    injected_at = (triggered or {}).get("injected_at")
    started_at = (cloud_started or {}).get("time")
    failed_at = (cloud_failed or {}).get("time")
    injection_time = _time(injected_at)
    cloud_start_time = _time(started_at)
    failure_time = _time(failed_at)
    check("injector_armed", armed is not None, "injector_armed event is missing")
    check("injector_triggered", triggered is not None, "external fault_injection_triggered event is missing")
    check("injector_targeted_the_logged_worker", bool(
        triggered and cloud_process_started
        and triggered.get("target_pid") == cloud_process_started.get("pid")
        and triggered.get("injector_pid") != triggered.get("target_pid")
    ), "injector PID does not match the Cloud worker PID recorded at startup")
    check("cloud_was_processing_at_injection", bool(
        triggered and cloud_started and cloud_start_time and injection_time
        and cloud_start_time <= injection_time
        and (target_task_id is None or target_task_id == cloud_task_id)
        and (triggered or {}).get("worker_started_at") == started_at
    ), "cloud task did not start before the external injection or task identity is inconsistent")
    check("cloud_did_not_finish", cloud_started is not None and cloud_finished is None,
          "cloud worker has a matching finished event; this is not an in-flight failure")
    check("framework_detected_same_task_failure", bool(
        cloud_failed and cloud_task_id and failed_task_id == cloud_task_id
        and failure_time and injection_time and failure_time >= injection_time
    ), "framework failure event does not match the injected task or occurs before injection")
    check("framework_failed_over_same_task", bool(
        failover and failover_task_id == cloud_task_id
        and _payload(failover).get("reason")
        and cloud_failed and cloud_failed.get("_line", 0) < failover.get("_line", 0)
    ), "framework did not record a cloud-to-edge failover for the failed task")
    check("edge_completed_same_task", bool(
        edge_finished and edge_task_id == cloud_task_id
        and edge_worker_started and edge_worker_finished
        and _payload(edge_worker_finished).get("task_id") == cloud_task_id
        and failover and failover.get("_line", 0) < edge_finished.get("_line", 0)
    ), "edge did not complete the same task with a matching worker record")
    check("controller_completed", bool(
        isinstance(state, dict) and state.get("status") == "completed"
        and any(item.get("event") == "run_completed" and same_run(item) for item in framework)
    ), "long-horizon controller did not persist completed status")

    artifact_path = root / "workspace" / "artifacts" / "recovered_result.json"
    artifact = _read_json(artifact_path)
    check("artifact_exists_and_is_json", artifact is not None, "recovered_result.json is missing or invalid")
    check("artifact_matches_recovered_task", bool(
        artifact and artifact.get("run_id") == run_id
        and artifact.get("task_id") == cloud_task_id
        and artifact.get("execution_node") == "edge-01"
    ), "recovered artifact does not identify the same run/task and Edge execution")
    expected_digest = (summary or {}).get("expected_payload_sha256")
    edge_digest = _payload(edge_finished).get("digest") if edge_finished else None
    worker_digest = (edge_worker_finished or {}).get("digest")
    check("artifact_digest_matches_edge_execution", bool(
        artifact and expected_digest and artifact.get("payload_sha256") == expected_digest
        and edge_digest == expected_digest and worker_digest == expected_digest
    ), "artifact digest does not match the expected input and both Edge execution records")

    if require_edge_log and not edge:
        failures.append("edge_worker_events.jsonl is required for the final bundle but was not supplied")
        checks["edge_log_present"] = False
    else:
        checks["edge_log_present"] = bool(edge)
        if not edge:
            warnings.append("edge worker log is absent; runtime recovery is proven locally but the evidence bundle is incomplete")

    cloud_task_records = [item for item in cloud if same_run(item) and item.get("event") in {"worker_task_started", "worker_task_finished"}]
    edge_task_records = [item for item in edge if same_run(item) and item.get("event") in {"worker_task_started", "worker_task_finished"}]
    cloud_hosts = {item.get("host") for item in cloud_task_records if item.get("host")}
    edge_hosts = {item.get("host") for item in edge_task_records if item.get("host")}
    cloud_fingerprints = {item.get("host_fingerprint") for item in cloud_task_records if item.get("host_fingerprint")}
    edge_fingerprints = {item.get("host_fingerprint") for item in edge_task_records if item.get("host_fingerprint")}
    distinct_hosts = bool(cloud_hosts and edge_hosts and cloud_hosts.isdisjoint(edge_hosts))
    distinct_fingerprints = bool(cloud_fingerprints and edge_fingerprints and cloud_fingerprints.isdisjoint(edge_fingerprints))
    checks["distinct_hosts_observed"] = distinct_hosts
    checks["distinct_host_fingerprints_observed"] = distinct_fingerprints
    if require_cross_host and not (distinct_hosts and distinct_fingerprints):
        failures.append("distinct Cloud and Edge hostnames and fingerprints are required for a cross-host claim")
    elif not distinct_hosts:
        warnings.append("Cloud and Edge logs use the same host; classify this run as a loopback control")

    expected_revision = (summary or {}).get("source_revision") or {}
    expected_version = (expected_revision.get("commit"), expected_revision.get("working_tree_sha256"))
    cloud_versions = {
        ((item.get("source_revision") or {}).get("commit"), (item.get("source_revision") or {}).get("working_tree_sha256"))
        for item in cloud_task_records
    }
    edge_versions = {
        ((item.get("source_revision") or {}).get("commit"), (item.get("source_revision") or {}).get("working_tree_sha256"))
        for item in edge_task_records
    }
    source_revisions_match = bool(
        expected_version[0] and expected_version[1]
        and cloud_versions == {expected_version}
        and edge_versions == {expected_version}
    )
    check("cloud_and_edge_source_revisions_match", source_revisions_match,
          "Cloud/Edge worker source commit or working-tree fingerprint does not match the framework run")

    if isinstance(manifest, dict):
        records = manifest.get("files", [])
        edge_log_path = root / "edge_worker_events.jsonl"
        edge_record = next((
            record for record in records
            if isinstance(record, dict)
            and str(record.get("path", "")).replace("\\", "/") == "edge_worker_events.jsonl"
        ), None)
        if register_edge_log and edge_log_path.is_file() and edge_record is None:
            edge_record = {
                "path": "edge_worker_events.jsonl",
                "bytes": edge_log_path.stat().st_size,
                "sha256": _sha256(edge_log_path),
            }
            records.append(edge_record)
            manifest["files"] = records
            (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        checks["edge_log_registered_in_manifest"] = bool(edge_record)
        if require_edge_log and not edge_record:
            failures.append("edge_worker_events.jsonl must be registered in manifest.json for final acceptance")
        manifest_ok = True
        for record in records if isinstance(records, list) else []:
            if not isinstance(record, dict):
                manifest_ok = False
                continue
            path = Path(str(record.get("path", "")))
            if not path.is_absolute():
                path = root / path
            try:
                path.resolve().relative_to(root)
            except ValueError:
                manifest_ok = False
                failures.append(f"manifest path escapes the run directory: {path}")
                continue
            try:
                valid = path.is_file() and path.stat().st_size == record.get("bytes") and _sha256(path) == record.get("sha256")
            except OSError:
                valid = False
            if not valid:
                manifest_ok = False
                failures.append(f"manifest hash/size mismatch: {path}")
        checks["manifest_hashes_valid"] = manifest_ok and bool(records)
        if not checks["manifest_hashes_valid"]:
            failures.append("manifest has no verifiable file records")
    else:
        checks["manifest_hashes_valid"] = False

    details = {
        "run_id": run_id,
        "target_task_id": target_task_id,
        "cloud_task_id": cloud_task_id,
        "injected_at": injected_at,
        "failure_at": failed_at,
        "cloud_hosts": sorted(cloud_hosts),
        "edge_hosts": sorted(edge_hosts),
        "cloud_host_fingerprints": sorted(cloud_fingerprints),
        "edge_host_fingerprints": sorted(edge_fingerprints),
        "supplemental_edge_log": ({
            "path": "edge_worker_events.jsonl",
            "sha256": _sha256(root / "edge_worker_events.jsonl"),
        } if (root / "edge_worker_events.jsonl").is_file() else None),
        "source_revision": (summary or {}).get("source_revision"),
    }
    return Verification(not failures, checks, failures, warnings, details)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a dynamic external fault-recovery evidence bundle")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--require-cross-host", action="store_true")
    parser.add_argument("--require-edge-log", action="store_true")
    parser.add_argument("--register-edge-log", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = verify_run(
        args.run_dir,
        require_cross_host=args.require_cross_host,
        require_edge_log=args.require_edge_log,
        register_edge_log=args.register_edge_log,
    )
    output = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
