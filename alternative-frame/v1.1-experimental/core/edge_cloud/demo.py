from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

from ..acceptance import AcceptanceEvaluator
from ..agents import Agent, AgentRegistry
from ..long_horizon import LongHorizonController, LongHorizonStore
from ..models import AgentResult, Plan, SubTask, utc_now
from ..orchestrator import Orchestrator
from .agent import RemoteNode, RoutedRemoteAgent


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_REMOTE_PAYLOAD = {
    "experiment": "dynamic-node-failure-recovery",
    "sample_ids": ["species-A-01", "species-B-02", "species-C-03"],
    "measurement": {"temperature_c": 21.5, "humidity_pct": 48},
}


def _payload_digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ReportWriter(Agent):
    role = "report_writer"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def run(self, task: SubTask, context) -> AgentResult:
        source = context.get("remote_digest")
        if source is None or source.status != "success":
            return AgentResult(task.id, "failed", failures=["successful remote digest dependency missing"])
        try:
            remote = json.loads(source.summary)
        except json.JSONDecodeError as exc:
            return AgentResult(task.id, "failed", failures=[f"invalid remote result: {exc}"])
        if remote.get("digest") != task.metadata.get("expected_remote_digest"):
            return AgentResult(task.id, "failed", failures=["remote result digest does not match the expected input digest"])
        relative = "artifacts/recovered_result.json"
        destination = (self.workspace / relative).resolve()
        if self.workspace.resolve() not in destination.parents:
            return AgentResult(task.id, "failed", failures=["artifact path escaped the run workspace"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = {
            "run_id": remote["run_id"],
            "task_id": remote["task_id"],
            "execution_node": remote["node_id"],
            "execution_role": remote["node_role"],
            "execution_host": remote["host"],
            "payload_sha256": remote["digest"],
            "payload_size_bytes": remote["payload_size_bytes"],
            "verified_at": utc_now(),
            "verification": "digest shape and run/task identity checked",
        }
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return AgentResult(
            subtask_id=task.id,
            status="success",
            summary="recovered result written and verified",
            artifacts=[relative],
            evidence=["remote digest length=64", "run_id and task_id present"],
            tool_records=[{
                "tool": "file_editor",
                "success": True,
                "arguments": {"action": "write", "path": relative},
                "metadata": {"artifacts": [relative]},
            }],
        )


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _probe(url: str, timeout: float = 1) -> dict:
    with urlopen(url.rstrip("/") + "/health", timeout=timeout) as response:
        payload = json.loads(response.read(4096))
    if payload.get("status") != "ready" or not payload.get("node_id"):
        raise RuntimeError(f"worker health response is invalid: {url}")
    return payload


def _wait_health(url: str, process: subprocess.Popen | None, timeout: float = 12) -> dict:
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"worker exited before becoming ready (exit={process.returncode})")
        try:
            return _probe(url)
        except (OSError, TimeoutError, URLError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(0.1)
    raise TimeoutError(f"worker did not become ready: {url}: {last_error}")


def _start_worker(role: str, node_id: str, port: int, delay: float, log_dir: Path, token: str, host: str):
    event_log = log_dir / f"{role}_worker_events.jsonl"
    stdout_path = log_dir / f"{role}_worker_stdout.log"
    stdout = stdout_path.open("ab")
    env = os.environ.copy()
    env["AF_EDGE_CLOUD_TOKEN"] = token
    process = subprocess.Popen(
        [
            sys.executable, "-m", "core.edge_cloud.worker",
            "--host", host, "--port", str(port), "--node-id", node_id, "--role", role,
            "--delay-seconds", str(delay), "--event-log", str(event_log),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=subprocess.STDOUT,
    )
    return process, stdout, event_log, f"http://127.0.0.1:{port}"


def _terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=4)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _elapsed_ms(start: str, end: str) -> float | None:
    try:
        first = datetime.fromisoformat(start.replace("Z", "+00:00"))
        second = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return round((second - first).total_seconds() * 1000, 3)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _git_revision() -> dict:
    try:
        repo_root = Path(subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip())
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root,
            capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        files = []
        for line in status:
            relative = line[3:] if len(line) > 3 else ""
            path = repo_root / relative
            if path.is_file():
                files.append({"path": relative.replace("\\", "/"), "sha256": _sha256(path)})
        files.sort(key=lambda item: item["path"])
        tree_material = json.dumps(files, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return {
            "branch": branch,
            "commit": commit,
            "working_tree_clean": not status,
            "working_tree_sha256": hashlib.sha256(tree_material).hexdigest(),
            "dirty_files": files,
        }
    except (OSError, subprocess.CalledProcessError):
        return {"branch": "unknown", "commit": "unknown"}


def run_experiment(
    evidence_root: Path,
    run_id: str | None = None,
    edge_url: str | None = None,
    injection_delay_seconds: float = 1.5,
    cloud_delay_seconds: float = 8,
    cloud_timeout_seconds: float = 3,
) -> dict:
    run_id = run_id or f"dynamic-fault-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:6]}"
    if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in run_id):
        raise ValueError("run_id may contain only letters, numbers, '-' and '_'")
    run_dir = evidence_root.resolve() / run_id
    if run_dir.exists():
        raise FileExistsError(f"evidence directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    workspace = run_dir / "workspace"
    workspace.mkdir()
    if edge_url and not os.environ.get("AF_EDGE_CLOUD_TOKEN"):
        raise ValueError("AF_EDGE_CLOUD_TOKEN must be set when using a separately started Edge worker")
    token = os.environ.get("AF_EDGE_CLOUD_TOKEN") or secrets.token_urlsafe(24)
    local_edge = edge_url is None
    edge_process = cloud_process = injector_process = None
    handles = []
    try:
        edge_process = None
        edge_event_path = None
        if local_edge:
            edge_process, edge_stdout, edge_event_path, local_edge_url = _start_worker(
                "edge", "edge-01", _free_port(), 0.02, run_dir, token, "127.0.0.1",
            )
            handles.append(edge_stdout)
            edge_url = local_edge_url
        edge_health = _wait_health(edge_url, edge_process)
        if edge_health.get("role") != "edge":
            raise RuntimeError("the configured fallback endpoint did not identify itself as an Edge worker")

        cloud_process, cloud_stdout, cloud_event_path, cloud_url = _start_worker(
            "cloud", "cloud-01", _free_port(), cloud_delay_seconds, run_dir, token, "127.0.0.1",
        )
        handles.append(cloud_stdout)
        cloud_health = _wait_health(cloud_url, cloud_process)
        if cloud_health.get("role") != "cloud":
            raise RuntimeError("the primary endpoint did not identify itself as a Cloud worker")

        injector_log = run_dir / "injector_events.jsonl"
        injector_stdout = (run_dir / "injector_stdout.log").open("ab")
        handles.append(injector_stdout)
        injector_env = os.environ.copy()
        injector_process = subprocess.Popen(
            [
                sys.executable, "-m", "core.edge_cloud.fault_injector",
                "--target-pid", str(cloud_process.pid),
                "--delay-seconds", str(injection_delay_seconds),
                "--event-log", str(injector_log),
                "--run-id", run_id, "--target-node", cloud_health["node_id"],
                "--target-task-id", "remote_digest",
                "--worker-event-log", str(cloud_event_path),
            ],
            cwd=PROJECT_ROOT,
            env=injector_env,
            stdin=subprocess.DEVNULL,
            stdout=injector_stdout,
            stderr=subprocess.STDOUT,
        )

        store = LongHorizonStore(run_dir / "framework_runs")

        def framework_event(event: str, payload: dict):
            store.append_event(run_id, event, payload)

        registry = AgentRegistry()
        registry.register(RoutedRemoteAgent(
            [
                RemoteNode(cloud_health["node_id"], cloud_health["role"], cloud_url),
                RemoteNode(edge_health["node_id"], edge_health["role"], edge_url),
            ],
            token=token,
            run_id=run_id,
            timeout_seconds=cloud_timeout_seconds,
            on_event=framework_event,
        ))
        registry.register(ReportWriter(workspace))
        orchestrator = Orchestrator(
            registry,
            acceptance=AcceptanceEvaluator(workspace),
        )
        plan = Plan(
            goal="Complete a remote task despite a dynamically injected cloud-node failure and verify the recovered artifact.",
            subtasks=[
                SubTask(
                    "remote_digest",
                    "remote_worker",
                    "Compute a SHA-256 digest for the experiment payload on the selected remote node.",
                    max_retries=0,
                    metadata={
                        "remote_payload": DEMO_REMOTE_PAYLOAD,
                        "expected_remote_digest": _payload_digest(DEMO_REMOTE_PAYLOAD),
                    },
                ),
                SubTask(
                    "write_report",
                    "report_writer",
                    "Write a verified result record using the remote task output.",
                    depends_on=["remote_digest"],
                    max_retries=0,
                    metadata={
                        "expected_remote_digest": _payload_digest(DEMO_REMOTE_PAYLOAD),
                        "expected_outputs": ["artifacts/recovered_result.json"],
                        "checks": [{
                            "id": "recovered_result_exists",
                            "check_type": "file_exists",
                            "path": "artifacts/recovered_result.json",
                        }],
                    },
                ),
            ],
        )
        controller = LongHorizonController(
            orchestrator,
            lambda _state: plan,
            store,
            max_phases=1,
            max_total_tasks=4,
            on_event=lambda event, payload: None,
            acceptance_contract={
                "goal": "remote node failure is recovered and verified",
                "required_artifacts": ["artifacts/recovered_result.json"],
            },
            workspace_path=str(workspace),
        )
        report = controller.run(
            "Complete a remote task despite a dynamically injected cloud-node failure and verify the recovered artifact.",
            run_id=run_id,
        )
        injector_exit = injector_process.wait(timeout=max(10, injection_delay_seconds + 5))
        if cloud_process.poll() is None:
            cloud_process.wait(timeout=2)
        state_path = store.state_path(run_id)
        framework_events = store.run_dir(run_id) / "events.jsonl"
        artifact = workspace / "artifacts" / "recovered_result.json"
        injector_events = _read_jsonl(injector_log)
        route_events = _read_jsonl(framework_events)
        cloud_events = _read_jsonl(cloud_event_path)
        injected = next((event for event in injector_events if event.get("event") == "fault_injection_triggered"), None)
        cloud_started = next((event for event in cloud_events if event.get("event") == "worker_task_started"), None)
        cloud_attempt_failed = next((event for event in route_events if event.get("event") == "remote_attempt_failed" and event.get("payload", {}).get("node_id") == "cloud-01"), None)
        failover = next((event for event in route_events if event.get("event") == "remote_failover" and event.get("payload", {}).get("from_node") == "cloud-01" and event.get("payload", {}).get("to_node") == "edge-01"), None)
        edge_completed = next((event for event in route_events if event.get("event") == "remote_task_completed" and event.get("payload", {}).get("node_id") == "edge-01"), None)
        cloud_finished = next((event for event in cloud_events if event.get("event") == "worker_task_finished"), None)
        injected_task_id = injected.get("target_task_id") if injected else None
        actual_task_id = cloud_started.get("task_id") if cloud_started else None
        cloud_attempt_task_id = cloud_attempt_failed.get("payload", {}).get("task_id") if cloud_attempt_failed else None
        edge_task_id = edge_completed.get("payload", {}).get("task_id") if edge_completed else None
        state = store.load(run_id)
        artifact_result = json.loads(artifact.read_text(encoding="utf-8")) if artifact.is_file() else {}
        checks = {
            "injector_triggered": injected is not None and injector_exit == 0,
            "injected_task_identity_matches": bool(
                injected and cloud_started and injected_task_id == actual_task_id == "remote_digest"
            ),
            "injector_targeted_cloud_worker_pid": bool(
                injected and any(event.get("event") == "worker_started" and event.get("pid") == injected.get("target_pid") for event in cloud_events)
                and injected.get("injector_pid") != injected.get("target_pid")
            ),
            "cloud_was_processing_at_injection": bool(
                cloud_started and injected and cloud_started.get("time", "") <= injected.get("injected_at", "")
            ),
            "framework_detected_failure_after_injection": bool(
                cloud_attempt_failed and injected
                and cloud_attempt_failed.get("time", "") >= injected.get("injected_at", "")
            ),
            "framework_observed_cloud_failure": cloud_attempt_failed is not None,
            "framework_failure_matches_injected_task": bool(
                cloud_attempt_task_id and cloud_attempt_task_id == actual_task_id
            ),
            "cloud_task_did_not_finish": cloud_started is not None and cloud_finished is None,
            "framework_failed_over_to_edge": failover is not None,
            "edge_completed_remote_task": bool(edge_completed and edge_task_id == actual_task_id),
            "long_horizon_controller_completed": report.status == "completed" and state.status == "completed",
            "required_artifact_exists": artifact.is_file(),
            "artifact_records_edge_execution": artifact_result.get("execution_node") == "edge-01",
            "artifact_digest_matches_task_input": artifact_result.get("payload_sha256") == _payload_digest(DEMO_REMOTE_PAYLOAD),
        }
        verification_passed = all(checks.values())
        summary = {
            "run_id": run_id,
            "generated_at": utc_now(),
            "evidence_kind": "controlled_external_process_fault_injection",
            "source_revision": _git_revision(),
            "network_scope": "single_host_loopback_control" if local_edge else (
                "distinct_hostnames_observed_unverified" if edge_health.get("host_fingerprint") != cloud_health.get("host_fingerprint")
                else "same_host_identity"
            ),
            "nodes": {"cloud": cloud_health, "edge": edge_health},
            "injection": injected or {"status": "missing"},
            "injection_delay_seconds": injection_delay_seconds,
            "failure_detection_latency_ms": (
                _elapsed_ms(injected.get("injected_at"), cloud_attempt_failed.get("time"))
                if injected and cloud_attempt_failed else None
            ),
            "edge_failover_latency_ms": (
                _elapsed_ms(injected.get("injected_at"), failover.get("time"))
                if injected and failover else None
            ),
            "long_horizon_status": report.status,
            "phase_count": len(state.phases),
            "framework_events_path": str(framework_events.relative_to(run_dir)),
            "injector_events_path": str(injector_log.relative_to(run_dir)),
            "cloud_worker_events_path": str(cloud_event_path.relative_to(run_dir)),
            "edge_worker_events_path": str(edge_event_path.relative_to(run_dir)) if edge_event_path else "edge_worker_events.jsonl (copy from Edge host after run)",
            "artifact_path": str(artifact.relative_to(run_dir)) if artifact.is_file() else None,
            "artifact_sha256": _sha256(artifact) if artifact.is_file() else None,
            "expected_payload_sha256": _payload_digest(DEMO_REMOTE_PAYLOAD),
            "checks": checks,
            "verification_passed": verification_passed,
            "evidence_bundle_status": "complete_for_loopback_control" if local_edge else "awaiting_copied_edge_worker_events_for_final_verification",
            "claim_boundary": (
                "Local process-level integration only; does not prove a second physical host."
                if local_edge else
                "Execution reached the separately configured Edge endpoint. This is not a cross-host acceptance until the copied Edge event log passes core.edge_cloud.evidence."
            ),
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest_paths = [injector_log, framework_events, cloud_event_path, state_path, artifact, summary_path]
        if edge_event_path:
            manifest_paths.append(edge_event_path)
        manifest_paths.extend([run_dir / "cloud_worker_stdout.log", run_dir / "injector_stdout.log"])
        if local_edge:
            manifest_paths.append(run_dir / "edge_worker_stdout.log")
        manifest = {
            "run_id": run_id,
            "generated_at": utc_now(),
            "files": [
                {"path": str(path.relative_to(run_dir)).replace("\\", "/"), "sha256": _sha256(path), "bytes": path.stat().st_size}
                for path in manifest_paths if path.is_file()
            ],
        }
        (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not verification_passed:
            raise RuntimeError(f"dynamic fault acceptance failed; see {summary_path}")
        return summary
    finally:
        _terminate(injector_process)
        _terminate(cloud_process)
        if local_edge:
            _terminate(edge_process)
        for handle in handles:
            try:
                handle.close()
            except OSError:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the main-framework dynamic edge/cloud fault-recovery acceptance")
    parser.add_argument("--evidence-dir", type=Path, default=Path("runs/dynamic_fault_injection"))
    parser.add_argument("--run-id")
    parser.add_argument("--edge-url", help="existing edge worker endpoint; omit to start a local control edge")
    parser.add_argument("--inject-delay-seconds", type=float, default=1.5)
    parser.add_argument("--cloud-delay-seconds", type=float, default=8)
    parser.add_argument("--cloud-timeout-seconds", type=float, default=3)
    args = parser.parse_args(argv)
    summary = run_experiment(
        args.evidence_dir,
        run_id=args.run_id,
        edge_url=args.edge_url,
        injection_delay_seconds=args.inject_delay_seconds,
        cloud_delay_seconds=args.cloud_delay_seconds,
        cloud_timeout_seconds=args.cloud_timeout_seconds,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
