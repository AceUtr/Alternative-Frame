from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..acceptance import AcceptanceEvaluator
from ..agents import Agent, AgentRegistry
from ..models import AgentResult, Plan, SubTask, utc_now
from ..orchestrator import Orchestrator
from .controller import LongHorizonController
from .evaluator import GoalEvaluation
from .state import LongHorizonState
from .store import LongHorizonStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHANGE_REQUEST = {
    "change_type": "acceptance_criteria_added",
    "new_revision": 2,
    "required_section": "limitations",
    "required_statement": "This controlled run is not evidence of a live API result.",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _append(path: Path, event: str, **payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"time": utc_now(), "event": event, **payload}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def inject_requirement_change(
    run_id: str,
    framework_events: Path,
    baseline_artifact: Path,
    inbox_path: Path,
    injector_log: Path,
    delay_seconds: float = 0.15,
    timeout_seconds: float = 20,
) -> int:
    """Wait for the baseline task, then publish a new criterion out of process."""
    if delay_seconds < 0 or timeout_seconds <= 0:
        raise ValueError("delay must be non-negative and timeout must be positive")
    _append(injector_log, "requirement_injector_armed", run_id=run_id, injector_pid=os.getpid())
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        baseline_done = any(
            row.get("event") == "task_finished"
            and (row.get("payload") or {}).get("phase") == 1
            and (row.get("payload") or {}).get("task_id") == "prepare_baseline"
            and ((row.get("payload") or {}).get("result") or {}).get("status") == "success"
            for row in _read_jsonl(framework_events)
        )
        if baseline_done and baseline_artifact.is_file():
            break
        time.sleep(0.02)
    else:
        _append(injector_log, "requirement_injection_failed", run_id=run_id, reason="baseline_task_not_observed")
        return 2

    baseline_hash = _sha256(baseline_artifact)
    time.sleep(delay_seconds)
    request_id = f"{run_id}-change-2"
    request = {
        "run_id": run_id,
        "request_id": request_id,
        "base_revision": 1,
        **CHANGE_REQUEST,
        "injected_at": utc_now(),
        "baseline_sha256_at_injection": baseline_hash,
    }
    request_bytes = json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")
    _write_json(inbox_path, request)
    _append(
        injector_log,
        "dynamic_requirement_injected",
        run_id=run_id,
        request_id=request_id,
        base_revision=1,
        new_revision=2,
        injected_at=request["injected_at"],
        requirement_sha256=hashlib.sha256(request_bytes).hexdigest(),
        baseline_sha256_at_injection=baseline_hash,
        injector_pid=os.getpid(),
    )
    return 0


class BaselineAgent(Agent):
    role = "baseline_writer"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def run(self, task: SubTask, context) -> AgentResult:
        relative = "artifacts/baseline_report.json"
        destination = self.workspace / relative
        report = {
            "run_id": task.metadata["run_id"],
            "revision": 1,
            "summary": "Initial controlled analysis report.",
            "created_at": utc_now(),
        }
        _write_json(destination, report)
        return AgentResult(
            task.id,
            "success",
            summary="baseline report generated",
            artifacts=[relative],
            evidence=["revision=1"],
            tool_records=[{
                "tool": "file_editor", "success": True,
                "arguments": {"action": "write", "path": relative},
                "metadata": {"artifacts": [relative]},
            }],
        )


class ChangeInboxAgent(Agent):
    role = "change_inbox_monitor"

    def __init__(self, inbox_path: Path, run_id: str, timeout_seconds: float):
        self.inbox_path = inbox_path
        self.run_id = run_id
        self.timeout_seconds = timeout_seconds

    def run(self, task: SubTask, context) -> AgentResult:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            try:
                request = json.loads(self.inbox_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.02)
                continue
            if request.get("run_id") != self.run_id or request.get("base_revision") != 1:
                time.sleep(0.02)
                continue
            _append(
                self.inbox_path.parent.parent / "framework_change_events.jsonl",
                "dynamic_requirement_detected",
                run_id=self.run_id,
                request_id=request.get("request_id"),
                detected_at=utc_now(),
                required_section=request.get("required_section"),
            )
            return AgentResult(
                task.id,
                "success",
                summary=json.dumps(request, ensure_ascii=False, sort_keys=True),
                evidence=["dynamic requirement detected from inbox", f"request_id={request['request_id']}"],
            )
        return AgentResult(task.id, "failed", failures=["dynamic requirement inbox timed out"])


class ChangeApplierAgent(Agent):
    role = "change_applier"

    def __init__(self, workspace: Path, inbox_path: Path, run_id: str):
        self.workspace = workspace
        self.inbox_path = inbox_path
        self.run_id = run_id

    def run(self, task: SubTask, context) -> AgentResult:
        baseline_path = self.workspace / "artifacts" / "baseline_report.json"
        destination = self.workspace / "artifacts" / "revised_report.json"
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            request = json.loads(self.inbox_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return AgentResult(task.id, "failed", failures=[f"required input could not be read: {type(exc).__name__}"])
        if request.get("run_id") != self.run_id or request.get("required_section") != "limitations":
            return AgentResult(task.id, "failed", failures=["unsupported or unrelated change request"])
        if baseline.get("run_id") != self.run_id or baseline.get("revision") != 1:
            return AgentResult(task.id, "failed", failures=["baseline artifact identity is invalid"])
        revised = {
            **baseline,
            "revision": request["new_revision"],
            "change_request_id": request["request_id"],
            "limitations": [request["required_statement"]],
            "updated_at": utc_now(),
        }
        _write_json(destination, revised)
        return AgentResult(
            task.id,
            "success",
            summary="new acceptance criterion applied to the existing baseline",
            artifacts=["artifacts/revised_report.json"],
            evidence=[f"change_request_id={request['request_id']}", "baseline artifact reused"],
            tool_records=[{
                "tool": "file_editor", "success": True,
                "arguments": {"action": "write", "path": "artifacts/revised_report.json"},
                "metadata": {"artifacts": ["artifacts/revised_report.json"]},
            }],
        )


class ChangeAcceptanceEvaluator:
    def __init__(self, workspace: Path, inbox_path: Path, run_id: str):
        self.workspace = workspace
        self.inbox_path = inbox_path
        self.run_id = run_id

    def evaluate(self, state: LongHorizonState, plan: Plan, report) -> GoalEvaluation:
        if report.status != "success":
            return GoalEvaluation(False, "phase execution failed", failures=list(report.failures))
        try:
            request = json.loads(self.inbox_path.read_text(encoding="utf-8"))
            baseline = json.loads((self.workspace / "artifacts/baseline_report.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return GoalEvaluation(False, "change or baseline evidence is missing", failures=[type(exc).__name__])
        if request.get("run_id") != self.run_id or baseline.get("run_id") != self.run_id:
            return GoalEvaluation(False, "run identity mismatch", failures=["cross-run evidence rejected"])
        revised_path = self.workspace / "artifacts/revised_report.json"
        if not revised_path.is_file():
            return GoalEvaluation(
                False,
                "dynamic acceptance criterion detected; revised plan required",
                missing_criteria=["revised_report contains the injected limitations section"],
                next_focus=[request["required_statement"]],
                evidence=[f"change_request_id={request['request_id']}", "baseline artifact retained"],
            )
        revised = json.loads(revised_path.read_text(encoding="utf-8"))
        accepted = (
            revised.get("change_request_id") == request.get("request_id")
            and revised.get("revision") == request.get("new_revision")
            and request.get("required_statement") in revised.get("limitations", [])
        )
        if not accepted:
            return GoalEvaluation(False, "injected acceptance criterion is not satisfied", missing_criteria=["required statement"])
        return GoalEvaluation(
            True,
            "injected acceptance criterion satisfied while retaining the baseline artifact",
            satisfied_criteria=["baseline report retained", "new limitations criterion present"],
            evidence=[f"change_request_id={request['request_id']}", "revised_report verified"],
        )


def _make_plan(state: LongHorizonState) -> Plan:
    run_id = state.run_id
    return Plan(
        goal="Produce a baseline report, detect an externally injected requirement change, and adapt the deliverable.",
        subtasks=[
            SubTask(
                "prepare_baseline", "baseline_writer", "Create the initial report under revision 1.",
                max_retries=0,
                metadata={
                    "run_id": run_id,
                    "expected_outputs": ["artifacts/baseline_report.json"],
                    "checks": [{"id": "baseline_exists", "check_type": "file_exists", "path": "artifacts/baseline_report.json"}],
                },
            ),
            SubTask(
                "wait_for_change", "change_inbox_monitor", "Monitor the run-scoped change inbox and record a newly received criterion.",
                depends_on=["prepare_baseline"], max_retries=0,
            ),
        ],
    )


def _replan_after_change(state: LongHorizonState, evaluation: GoalEvaluation) -> Plan:
    return Plan(
        goal="Apply the newly injected requirement without regenerating the accepted baseline report.",
        subtasks=[
            SubTask(
                "apply_change", "change_applier", "Update the report to satisfy the injected criterion while preserving the baseline.",
                max_retries=0,
                metadata={
                    "expected_outputs": ["artifacts/revised_report.json"],
                    "checks": [{"id": "revised_report_exists", "check_type": "file_exists", "path": "artifacts/revised_report.json"}],
                },
            ),
        ],
    )


def run_experiment(evidence_root: Path, run_id: str | None = None, injection_delay_seconds: float = 0.15) -> dict[str, Any]:
    run_id = run_id or f"dynamic-change-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid4().hex[:6]}"
    if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in run_id):
        raise ValueError("run_id may contain only letters, numbers, '-' and '_'")
    run_dir = evidence_root.resolve() / run_id
    if run_dir.exists():
        raise FileExistsError(f"evidence directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    workspace = run_dir / "workspace"
    workspace.mkdir()
    inbox_path = run_dir / "inbox" / "change_request.json"
    framework_root = run_dir / "framework_runs"
    framework_events = framework_root / run_id / "events.jsonl"
    baseline_path = workspace / "artifacts/baseline_report.json"
    injector_log = run_dir / "change_injector_events.jsonl"
    injector_stdout = (run_dir / "change_injector_stdout.log").open("ab")
    injector = subprocess.Popen(
        [
            sys.executable, "-m", "core.long_horizon.dynamic_change_demo", "--inject-only",
            "--run-id", run_id,
            "--framework-events", str(framework_events),
            "--baseline-artifact", str(baseline_path),
            "--inbox", str(inbox_path),
            "--injector-log", str(injector_log),
            "--delay-seconds", str(injection_delay_seconds),
        ],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=injector_stdout,
        stderr=subprocess.STDOUT,
    )
    try:
        store = LongHorizonStore(framework_root)
        registry = AgentRegistry()
        registry.register(BaselineAgent(workspace))
        registry.register(ChangeInboxAgent(inbox_path, run_id, timeout_seconds=15))
        registry.register(ChangeApplierAgent(workspace, inbox_path, run_id))
        orchestrator = Orchestrator(registry, acceptance=AcceptanceEvaluator(workspace))
        controller = LongHorizonController(
            orchestrator,
            _make_plan,
            store,
            evaluator=ChangeAcceptanceEvaluator(workspace, inbox_path, run_id),
            replanner=_replan_after_change,
            max_phases=2,
            max_total_tasks=4,
            acceptance_contract={
                "revision": 1,
                "required_artifacts": ["artifacts/baseline_report.json", "artifacts/revised_report.json"],
                "dynamic_change_policy": "retain valid prior artifacts and replan only the changed requirement",
            },
            workspace_path=str(workspace),
        )
        report = controller.run(
            "Produce a controlled analysis report and adapt it to a requirement injected during execution.",
            run_id=run_id,
        )
        injector_exit = injector.wait(timeout=20)
        state = store.load(run_id)
        injector_events = _read_jsonl(injector_log)
        change_event = next((row for row in injector_events if row.get("event") == "dynamic_requirement_injected"), None)
        framework_change_events = _read_jsonl(run_dir / "framework_change_events.jsonl")
        detected = next((row for row in framework_change_events if row.get("event") == "dynamic_requirement_detected"), None)
        baseline_hash = _sha256(baseline_path) if baseline_path.is_file() else None
        revised_path = workspace / "artifacts/revised_report.json"
        revised = json.loads(revised_path.read_text(encoding="utf-8")) if revised_path.is_file() else {}
        checks = {
            "external_injector_succeeded": injector_exit == 0 and change_event is not None,
            "change_arrived_after_baseline_completed": bool(
                change_event and detected
                and change_event.get("baseline_sha256_at_injection")
                and change_event.get("baseline_sha256_at_injection") == baseline_hash
            ),
            "framework_detected_same_change": bool(
                change_event and detected
                and change_event.get("request_id") == detected.get("request_id")
            ),
            "controller_replanned": bool(
                len(state.phases) == 2
                and state.phases[0].status == "incomplete"
                and "apply_change" in state.phases[1].task_ids
            ),
            "baseline_artifact_retained": bool(
                baseline_hash and change_event
                and baseline_hash == change_event.get("baseline_sha256_at_injection")
            ),
            "new_requirement_satisfied": bool(
                revised.get("revision") == 2
                and revised.get("change_request_id") == (change_event or {}).get("request_id")
                and CHANGE_REQUEST["required_statement"] in revised.get("limitations", [])
            ),
            "controller_completed": report.status == "completed" and state.status == "completed",
            "no_manual_pause_or_resume": not any(
                row.get("event") in {"run_paused", "run_resumed", "human_intervention"}
                for row in _read_jsonl(framework_events)
            ),
        }
        summary = {
            "run_id": run_id,
            "generated_at": utc_now(),
            "evidence_kind": "external_mid_run_acceptance_criteria_change",
            "network_scope": "single_host_control",
            "source_revision": _source_revision(),
            "injected_change": change_event,
            "detected_change": detected,
            "long_horizon_status": report.status,
            "phase_count": len(state.phases),
            "baseline_artifact": "workspace/artifacts/baseline_report.json",
            "baseline_sha256": baseline_hash,
            "revised_artifact": "workspace/artifacts/revised_report.json" if revised_path.is_file() else None,
            "revised_sha256": _sha256(revised_path) if revised_path.is_file() else None,
            "checks": checks,
            "verification_passed": all(checks.values()),
            "manifest_path": "manifest.json",
            "claim_boundary": "Deterministic local change-inbox demonstration; it proves controller replanning and artifact retention, not model-generated change interpretation or a remote deployment.",
        }
        summary_path = run_dir / "summary.json"
        _write_json(summary_path, summary)
        files = [
            injector_log,
            run_dir / "framework_change_events.jsonl",
            framework_events,
            store.state_path(run_id),
            inbox_path,
            baseline_path,
            revised_path,
            summary_path,
        ]
        manifest = {
            "run_id": run_id,
            "generated_at": utc_now(),
            "files": [
                {"path": str(path.relative_to(run_dir)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": _sha256(path)}
                for path in files if path.is_file()
            ],
        }
        _write_json(run_dir / "manifest.json", manifest)
        if not summary["verification_passed"]:
            raise RuntimeError(f"dynamic change acceptance failed: {json.dumps(checks, ensure_ascii=False)}")
        return summary
    finally:
        if injector.poll() is None:
            injector.terminate()
            injector.wait(timeout=3)
        injector_stdout.close()


def _source_revision() -> dict[str, Any]:
    try:
        repo_root = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip())
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root, capture_output=True, text=True, check=True).stdout.splitlines()
        dirty_files = []
        for line in status:
            relative = line[3:] if len(line) > 3 else ""
            path = repo_root / relative
            if path.is_file():
                dirty_files.append({"path": relative.replace("\\", "/"), "sha256": _sha256(path)})
        dirty_files.sort(key=lambda item: item["path"])
        return {
            "branch": branch,
            "commit": commit,
            "working_tree_clean": not status,
            "dirty_files": dirty_files,
            "working_tree_sha256": hashlib.sha256(json.dumps(dirty_files, sort_keys=True).encode("utf-8")).hexdigest(),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"branch": "unknown", "commit": "unknown", "working_tree_clean": False}


def verify_run(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    failures = []
    hash_checks = []
    for row in manifest.get("files", []):
        path = root / row["path"]
        try:
            path.resolve().relative_to(root)
            valid = path.is_file() and path.stat().st_size == row.get("bytes") and _sha256(path) == row.get("sha256")
        except (OSError, ValueError):
            valid = False
        hash_checks.append(valid)
        if not valid:
            failures.append(f"manifest mismatch: {row.get('path')}")
    run_id = summary.get("run_id")
    request = json.loads((root / "inbox/change_request.json").read_text(encoding="utf-8"))
    injected_events = _read_jsonl(root / "change_injector_events.jsonl")
    detected_events = _read_jsonl(root / "framework_change_events.jsonl")
    framework_events = _read_jsonl(root / "framework_runs" / run_id / "events.jsonl")
    state = json.loads((root / "framework_runs" / run_id / "state.json").read_text(encoding="utf-8"))
    injected = next((row for row in injected_events if row.get("event") == "dynamic_requirement_injected"), None)
    detected = next((row for row in detected_events if row.get("event") == "dynamic_requirement_detected"), None)
    baseline_finished = next((
        row for row in framework_events
        if row.get("event") == "task_finished"
        and (row.get("payload") or {}).get("phase") == 1
        and (row.get("payload") or {}).get("task_id") == "prepare_baseline"
        and ((row.get("payload") or {}).get("result") or {}).get("status") == "success"
    ), None)
    phase_two_plan = next((
        row for row in framework_events
        if row.get("event") == "phase_planned"
        and (row.get("payload") or {}).get("phase") == 2
        and any(task.get("id") == "apply_change" for task in (row.get("payload") or {}).get("tasks", []))
    ), None)
    baseline_path = root / "workspace/artifacts/baseline_report.json"
    revised_path = root / "workspace/artifacts/revised_report.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.is_file() else {}
    revised = json.loads(revised_path.read_text(encoding="utf-8")) if revised_path.is_file() else {}
    requirement_hash = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    checks = {
        "run_identity_matches": bool(run_id and request.get("run_id") == run_id and injected and injected.get("run_id") == run_id),
        "external_injection_after_baseline": bool(
            baseline_finished and injected
            and baseline_finished.get("time", "") <= injected.get("injected_at", "")
            and injected.get("baseline_sha256_at_injection") == _sha256(baseline_path)
        ),
        "framework_detected_injected_change": bool(
            injected and detected and injected.get("request_id") == detected.get("request_id")
            and injected.get("injected_at", "") <= detected.get("detected_at", "")
        ),
        "controller_planned_second_phase": phase_two_plan is not None,
        "baseline_retained": bool(baseline.get("revision") == 1 and injected and injected.get("baseline_sha256_at_injection") == _sha256(baseline_path)),
        "new_criterion_satisfied": bool(
            revised.get("revision") == request.get("new_revision")
            and revised.get("change_request_id") == request.get("request_id")
            and request.get("required_statement") in revised.get("limitations", [])
        ),
        "run_completed_without_manual_pause": state.get("status") == "completed" and not any(
            row.get("event") in {"run_paused", "run_resumed", "human_intervention"} for row in framework_events
        ),
        "manifest_hashes_valid": bool(hash_checks) and all(hash_checks),
        "injected_requirement_hash_matches": bool(injected and injected.get("requirement_sha256") == requirement_hash),
    }
    result = {
        "run_id": summary.get("run_id"),
        "checks": checks,
        "failures": failures,
    }
    result["passed"] = all(checks.values()) and not failures
    if not result["passed"]:
        result["failures"].extend(name for name, passed in checks.items() if not passed)
    return result


def _inject_only(args) -> int:
    return inject_requirement_change(
        args.run_id,
        args.framework_events,
        args.baseline_artifact,
        args.inbox,
        args.injector_log,
        args.delay_seconds,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run dynamic requirement-change and long-horizon replanning acceptance")
    parser.add_argument("--evidence-dir", type=Path, default=Path("runs/dynamic_requirement_change"))
    parser.add_argument("--run-id")
    parser.add_argument("--delay-seconds", type=float, default=0.15)
    parser.add_argument("--inject-only", action="store_true")
    parser.add_argument("--verify-run", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--framework-events", type=Path)
    parser.add_argument("--baseline-artifact", type=Path)
    parser.add_argument("--inbox", type=Path)
    parser.add_argument("--injector-log", type=Path)
    args = parser.parse_args(argv)
    if args.verify_run:
        result = verify_run(args.verify_run)
        output = json.dumps(result, ensure_ascii=False, indent=2)
        print(output)
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
        return 0 if result["passed"] else 1
    if args.inject_only:
        if not all((args.run_id, args.framework_events, args.baseline_artifact, args.inbox, args.injector_log)):
            parser.error("inject-only requires run ID, framework event file, baseline artifact, inbox and injector log")
        return _inject_only(args)
    summary = run_experiment(args.evidence_dir, args.run_id, args.delay_seconds)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
