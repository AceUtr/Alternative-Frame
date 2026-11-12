from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..agents import Agent, AgentRegistry
from ..models import AgentResult, Plan, SubTask, utc_now
from ..orchestrator import Orchestrator
from ..source_revision import describe_source_revision, sha256_file
from .acceptance_contract import AcceptanceContract, GoalCriterion
from .controller import LongHorizonController
from .global_evaluator import DeterministicGlobalEvaluator
from .runtime_changes import RuntimeChangeInbox, submit_change
from .store import LongHorizonStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOAL = "Create a baseline report, adapt it to a requirement injected during execution, and verify both versions."
REQUIRED_OUTPUT = "artifacts/final_report.json"
CRITERION_ID = "runtime_final_report"


def _append(path: Path, event: str, **payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": utc_now(), "event": event, **payload}, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def inject_runtime_requirement(
    run_id: str,
    framework_run_dir: Path,
    injector_log: Path,
    baseline_artifact: Path,
    delay_seconds: float = 0.2,
    timeout_seconds: float = 30,
) -> int:
    """Inject a new file acceptance criterion from a separate process."""
    if delay_seconds < 0 or timeout_seconds <= 0:
        raise ValueError("delay must be non-negative and timeout must be positive")
    _append(injector_log, "injector_armed", run_id=run_id, injector_pid=os.getpid())
    deadline = time.monotonic() + timeout_seconds
    baseline_event = None
    events_path = framework_run_dir / "events.jsonl"
    while time.monotonic() < deadline:
        baseline_event = next((
            row for row in _read_jsonl(events_path)
            if row.get("event") == "task_finished"
            and (row.get("payload") or {}).get("phase") == 1
            and (row.get("payload") or {}).get("task_id") == "prepare_baseline"
            and ((row.get("payload") or {}).get("result") or {}).get("status") == "success"
        ), None)
        if baseline_event and baseline_artifact.is_file():
            break
        time.sleep(0.03)
    else:
        _append(injector_log, "injection_failed", run_id=run_id, reason="baseline_success_not_observed")
        return 2

    time.sleep(delay_seconds)
    request = {
        "schema_version": 1,
        "run_id": run_id,
        "request_id": f"{run_id}-requirement-2",
        "base_revision": 1,
        "description": "Add a final report that incorporates the external requirement and preserves the baseline.",
        "add_criteria": [{
            "id": CRITERION_ID,
            "description": "The final report artifact exists and is produced by this run.",
            "check_type": "file_exists",
            "required": True,
            "path": REQUIRED_OUTPUT,
        }],
        "add_constraints": ["Retain the baseline report and record the injected request ID in the final report."],
    }
    injection_started_at = utc_now()
    _append(
        injector_log,
        "requirement_injection_started",
        run_id=run_id,
        request_id=request["request_id"],
        injection_started_at=injection_started_at,
        injector_pid=os.getpid(),
    )
    try:
        request_path = submit_change(framework_run_dir, request)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        _append(
            injector_log,
            "injection_failed",
            run_id=run_id,
            reason=f"{type(exc).__name__}: {exc}",
            injector_pid=os.getpid(),
        )
        return 3
    _append(
        injector_log,
        "runtime_requirement_injected",
        run_id=run_id,
        request_id=request["request_id"],
        request_sha256=sha256_file(request_path),
        baseline_sha256=sha256_file(baseline_artifact),
        baseline_task_finished_at=baseline_event.get("time"),
        injection_started_at=injection_started_at,
        injector_pid=os.getpid(),
    )
    return 0


class BaselineAgent(Agent):
    role = "baseline_writer"

    def __init__(self, workspace: Path, run_id: str):
        self.workspace = workspace
        self.run_id = run_id

    def run(self, task: SubTask, context) -> AgentResult:
        path = self.workspace / "artifacts" / "baseline_report.json"
        _write_json(path, {
            "run_id": self.run_id,
            "revision": 1,
            "result": "baseline created before external requirement injection",
            "created_at": utc_now(),
        })
        return AgentResult(
            task.id, "success", summary="baseline artifact created",
            artifacts=["artifacts/baseline_report.json"],
            evidence=["baseline_revision=1"],
        )


class ChangeMonitorAgent(Agent):
    role = "change_monitor"

    def __init__(self, inbox: Path, run_id: str, timeout_seconds: float = 30):
        self.inbox = inbox
        self.run_id = run_id
        self.timeout_seconds = timeout_seconds

    def run(self, task: SubTask, context) -> AgentResult:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            for path in sorted(self.inbox.glob("*.json")):
                try:
                    request = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if request.get("run_id") == self.run_id:
                    return AgentResult(
                        task.id, "success", summary="external request arrived during phase execution",
                        evidence=[f"request_id={request.get('request_id')}", "request arrived before phase boundary"],
                    )
            time.sleep(0.03)
        return AgentResult(task.id, "failed", failures=["external runtime requirement was not received"])


class FinalReportAgent(Agent):
    role = "final_report_writer"

    def __init__(self, workspace: Path, run_id: str):
        self.workspace = workspace
        self.run_id = run_id

    def run(self, task: SubTask, context) -> AgentResult:
        baseline_path = self.workspace / "artifacts" / "baseline_report.json"
        request_path = Path(task.metadata["request_path"])
        output_path = self.workspace / REQUIRED_OUTPUT
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            request = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            return AgentResult(task.id, "failed", failures=[f"baseline or accepted request unavailable: {type(exc).__name__}"])
        if baseline.get("run_id") != self.run_id or request.get("run_id") != self.run_id:
            return AgentResult(task.id, "failed", failures=["run identity mismatch"])
        if request.get("request_id") != task.metadata.get("request_id"):
            return AgentResult(task.id, "failed", failures=["request identity mismatch"])
        _write_json(output_path, {
            "run_id": self.run_id,
            "revision": 2,
            "baseline_sha256": sha256_file(baseline_path),
            "request_id": request["request_id"],
            "applied_criterion_ids": [criterion["id"] for criterion in request["add_criteria"]],
            "result": "updated final report preserving the baseline artifact",
            "created_at": utc_now(),
        })
        return AgentResult(
            task.id, "success", summary="final report incorporates accepted runtime change",
            artifacts=[REQUIRED_OUTPUT],
            evidence=[f"request_id={request['request_id']}", "baseline retained"],
        )


def _initial_plan(_state) -> Plan:
    return Plan(
        goal="Create a baseline artifact and stay active until a runtime change arrives.",
        subtasks=[
            SubTask(
                "prepare_baseline", "baseline_writer", "Create the initial report.",
                max_retries=0,
                metadata={
                    "expected_outputs": ["artifacts/baseline_report.json"],
                    "checks": [{"id": "baseline_exists", "check_type": "file_exists", "path": "artifacts/baseline_report.json"}],
                },
            ),
            SubTask(
                "wait_for_change", "change_monitor", "Wait for the externally injected requirement.",
                depends_on=["prepare_baseline"], max_retries=0,
            ),
        ],
    )


def _replan_after_change(state, evaluation) -> Plan:
    if not state.runtime_changes:
        raise RuntimeError("cannot replan without an applied runtime change")
    change = state.runtime_changes[-1]
    accepted_path = Path(change["request_path"])
    request = json.loads(accepted_path.read_text(encoding="utf-8"))
    criterion_ids = {item["id"] for item in request["add_criteria"]}
    if CRITERION_ID not in criterion_ids:
        raise RuntimeError("the applied request does not contain the expected criterion")
    return Plan(
        goal="Generate the final report required by the newly added acceptance criterion.",
        subtasks=[SubTask(
            "publish_final_report", "final_report_writer", "Preserve baseline and produce the new final report.",
            max_retries=0,
            metadata={
                "request_path": str(accepted_path),
                "request_id": request["request_id"],
                "expected_outputs": [REQUIRED_OUTPUT],
                "checks": [{"id": "final_report_exists", "check_type": "file_exists", "path": REQUIRED_OUTPUT}],
            },
        )],
    )


def run_experiment(evidence_root: str | Path, run_id: str | None = None, injection_delay_seconds: float = 0.2) -> dict[str, Any]:
    run_id = run_id or f"runtime-change-{int(time.time())}-{uuid4().hex[:6]}"
    if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in run_id):
        raise ValueError("run_id may contain only letters, numbers, '-' and '_'")
    evidence_root = Path(evidence_root).resolve()
    run_dir = evidence_root / run_id
    if run_dir.exists():
        raise FileExistsError(f"evidence directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    workspace = run_dir / "workspace"
    workspace.mkdir()
    framework_root = run_dir / "framework_runs"
    store = LongHorizonStore(framework_root)
    framework_run_dir = store.run_dir(run_id)
    injector_log = run_dir / "injector_events.jsonl"
    baseline_artifact = workspace / "artifacts" / "baseline_report.json"
    injector_stdout_path = run_dir / "injector_stdout.log"
    injector_stdout = injector_stdout_path.open("ab")
    injector = subprocess.Popen(
        [
            sys.executable, "-m", "core.long_horizon.runtime_change_acceptance", "--inject-only",
            "--run-id", run_id,
            "--framework-run-dir", str(framework_run_dir),
            "--injector-log", str(injector_log),
            "--baseline-artifact", str(baseline_artifact),
            "--delay-seconds", str(injection_delay_seconds),
        ],
        cwd=PROJECT_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=injector_stdout,
        stderr=subprocess.STDOUT,
    )
    try:
        registry = AgentRegistry()
        registry.register(BaselineAgent(workspace, run_id))
        registry.register(ChangeMonitorAgent(framework_run_dir / "runtime_changes" / "pending", run_id))
        registry.register(FinalReportAgent(workspace, run_id))
        contract = AcceptanceContract(
            goal=GOAL,
            goal_summary=GOAL,
            criteria=[GoalCriterion(
                id="baseline_report",
                description="Baseline report exists and was produced by this run.",
                check_type="file_exists",
                path="artifacts/baseline_report.json",
            )],
        )
        controller = LongHorizonController(
            Orchestrator(registry),
            _initial_plan,
            store,
            evaluator=DeterministicGlobalEvaluator(contract, workspace),
            replanner=_replan_after_change,
            max_phases=2,
            max_total_tasks=4,
            acceptance_contract=contract.to_dict(),
            workspace_path=str(workspace),
            runtime_change_inbox=RuntimeChangeInbox(framework_run_dir / "runtime_changes"),
        )
        report = controller.run(GOAL, run_id=run_id)
        injector_exit = injector.wait(timeout=35)
        state = store.load(run_id)
        framework_events_path = framework_run_dir / "events.jsonl"
        events = _read_jsonl(framework_events_path)
        injector_events = _read_jsonl(injector_log)
        applied = next((row for row in events if row.get("event") == "runtime_change_applied"), None)
        injected = next((row for row in injector_events if row.get("event") == "runtime_requirement_injected"), None)
        baseline_hash = sha256_file(baseline_artifact) if baseline_artifact.is_file() else None
        final_artifact = workspace / REQUIRED_OUTPUT
        final = json.loads(final_artifact.read_text(encoding="utf-8")) if final_artifact.is_file() else {}
        first_phase = next((phase for phase in state.phases if phase.number == 1), None)
        second_phase = next((phase for phase in state.phases if phase.number == 2), None)
        applied_record = next((item for item in state.runtime_changes if item.get("request_id") == f"{run_id}-requirement-2"), None)
        accepted_request = framework_run_dir / "runtime_changes" / "accepted" / f"{run_id}-requirement-2.json"
        checks = {
            "external_injector_succeeded": injector_exit == 0 and injected is not None,
            "injection_followed_baseline_success": bool(injected and baseline_hash == injected.get("baseline_sha256")),
            "separate_injector_process": bool(injected and injected.get("injector_pid") != os.getpid()),
            "injection_between_phase_tasks": bool(
                injected
                and injected.get("baseline_task_finished_at", "") <= injected.get("injection_started_at", "")
                and injected.get("injection_started_at", "") <= next((row.get("time", "") for row in events
                    if row.get("event") == "task_finished"
                    and (row.get("payload") or {}).get("task_id") == "wait_for_change"), "")
            ),
            "controller_applied_change_at_revision_2": bool(
                applied and applied_record and applied.get("payload", {}).get("revision") == 2
                and state.contract_revision == 2
            ),
            "first_phase_rejected_stale_completion": bool(
                first_phase and first_phase.status == "incomplete"
                and first_phase.evaluation.get("completed") is False
                and CRITERION_ID in first_phase.evaluation.get("missing_criteria", [])
                and first_phase.contract_revision == 2
            ),
            "controller_replanned_second_phase": bool(
                second_phase and second_phase.task_ids == ["publish_final_report"]
                and second_phase.status == "accepted" and second_phase.contract_revision == 2
            ),
            "baseline_retained": bool(baseline_hash and final.get("baseline_sha256") == baseline_hash),
            "new_requirement_in_final_artifact": bool(
                final.get("run_id") == run_id
                and final.get("request_id") == f"{run_id}-requirement-2"
                and CRITERION_ID in final.get("applied_criterion_ids", [])
            ),
            "long_horizon_completed": report.status == "completed" and state.status == "completed",
            "no_manual_pause_or_resume": not any(
                row.get("event") in {"run_paused", "run_resumed", "human_intervention"}
                for row in events
            ),
        }
        summary = {
            "run_id": run_id,
            "generated_at": utc_now(),
            "evidence_kind": "external_runtime_requirement_change_main_controller",
            "network_scope": "single_host_external_process_control",
            "source_revision": describe_source_revision(PROJECT_ROOT),
            "controller_pid": os.getpid(),
            "injected_request": injected,
            "applied_change": applied.get("payload") if applied else None,
            "final_status": state.status,
            "phase_count": state.phase,
            "contract_revision": state.contract_revision,
            "paths": {
                "framework_state": f"framework_runs/{run_id}/state.json",
                "framework_events": f"framework_runs/{run_id}/events.jsonl",
                "injector_events": "injector_events.jsonl",
                "accepted_request": str(accepted_request.relative_to(run_dir)).replace("\\", "/"),
                "baseline_artifact": "workspace/artifacts/baseline_report.json",
                "final_artifact": f"workspace/{REQUIRED_OUTPUT}",
            },
            "sha256": {
                "baseline_artifact": baseline_hash,
                "final_artifact": sha256_file(final_artifact) if final_artifact.is_file() else None,
                "accepted_request": sha256_file(accepted_request) if accepted_request.is_file() else None,
            },
            "checks": checks,
            "verification_passed": all(checks.values()),
            "claim_boundary": "Deterministic controlled run through the main long-horizon controller and a separate local injector process. It verifies additive contract revision, re-evaluation, replanning, and artifact retention; it is neither a live-API quality result nor a second-host deployment result.",
        }
        summary_path = run_dir / "summary.json"
        _write_json(summary_path, summary)
        manifest_paths = [
            framework_run_dir / "state.json",
            framework_events_path,
            accepted_request,
            framework_run_dir / "runtime_changes" / "contracts" / "revision-0001.json",
            framework_run_dir / "runtime_changes" / "contracts" / "revision-0002.json",
            injector_log,
            injector_stdout_path,
            baseline_artifact,
            final_artifact,
            summary_path,
        ]
        manifest = {
            "run_id": run_id,
            "source_revision": summary["source_revision"],
            "files": [
                {
                    "path": str(path.relative_to(run_dir)).replace("\\", "/"),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
                for path in manifest_paths if path.is_file()
            ],
        }
        _write_json(run_dir / "manifest.json", manifest)
        verification = verify_run(run_dir)
        summary["independent_verification"] = verification
        _write_json(summary_path, summary)
        manifest["files"] = [
            {
                "path": str(path.relative_to(run_dir)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in manifest_paths if path.is_file()
        ]
        _write_json(run_dir / "manifest.json", manifest)
        verification = verify_run(run_dir)
        if not summary["verification_passed"] or not verification["passed"]:
            raise RuntimeError(f"runtime change acceptance failed; inspect {summary_path} and verifier output")
        return summary
    finally:
        if injector.poll() is None:
            injector.terminate()
            injector.wait(timeout=3)
        injector_stdout.close()


def verify_run(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    try:
        summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        run_id = summary["run_id"]
        state = json.loads((root / "framework_runs" / run_id / "state.json").read_text(encoding="utf-8"))
        framework_events = _read_jsonl(root / "framework_runs" / run_id / "events.jsonl")
        injector_events = _read_jsonl(root / "injector_events.jsonl")
        baseline = json.loads((root / "workspace/artifacts/baseline_report.json").read_text(encoding="utf-8"))
        final = json.loads((root / "workspace" / REQUIRED_OUTPUT).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"passed": False, "checks": {}, "failures": [f"required evidence missing or invalid: {type(exc).__name__}: {exc}"]}

    manifest_checks = []
    for row in manifest.get("files", []):
        path = root / row.get("path", "")
        try:
            path.resolve().relative_to(root)
            manifest_checks.append(
                path.is_file() and path.stat().st_size == row.get("bytes") and sha256_file(path) == row.get("sha256")
            )
        except (OSError, ValueError):
            manifest_checks.append(False)
    injected = next((row for row in injector_events if row.get("event") == "runtime_requirement_injected"), None)
    applied = next((row for row in framework_events if row.get("event") == "runtime_change_applied"), None)
    baseline_finished = next((row for row in framework_events
        if row.get("event") == "task_finished"
        and (row.get("payload") or {}).get("task_id") == "prepare_baseline"
        and ((row.get("payload") or {}).get("result") or {}).get("status") == "success"), None)
    wait_finished = next((row for row in framework_events
        if row.get("event") == "task_finished"
        and (row.get("payload") or {}).get("task_id") == "wait_for_change"), None)
    phases = state.get("phases", [])
    first = next((row for row in phases if row.get("number") == 1), None)
    second = next((row for row in phases if row.get("number") == 2), None)
    criterion_id = CRITERION_ID
    request_id = f"{run_id}-requirement-2"
    accepted_path = root / "framework_runs" / run_id / "runtime_changes" / "accepted" / f"{request_id}.json"
    try:
        accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        accepted = {}
    checks = {
        "manifest_hashes_valid": bool(manifest_checks) and all(manifest_checks),
        "injector_recorded_external_request": bool(injected and injected.get("run_id") == run_id),
        "injector_was_separate_process": bool(
            injected and injected.get("injector_pid") != summary.get("controller_pid")
        ),
        "injected_while_first_phase_was_active": bool(
            injected and baseline_finished and wait_finished
            and baseline_finished.get("time", "") <= injected.get("injection_started_at", "") <= wait_finished.get("time", "")
            and injected.get("baseline_task_finished_at") == baseline_finished.get("time")
        ),
        "request_hash_matches_accepted_snapshot": bool(
            injected and accepted_path.is_file() and sha256_file(accepted_path) == injected.get("request_sha256")
        ),
        "controller_applied_revision_2": bool(
            applied and applied.get("payload", {}).get("request_id") == request_id
            and applied.get("payload", {}).get("revision") == 2
            and state.get("contract_revision") == 2
        ),
        "first_phase_is_incomplete_under_new_contract": bool(
            first and first.get("status") == "incomplete"
            and first.get("contract_revision") == 2
            and first.get("evaluation", {}).get("completed") is False
            and criterion_id in first.get("evaluation", {}).get("missing_criteria", [])
        ),
        "second_phase_completed_new_contract": bool(
            second and second.get("status") == "accepted"
            and second.get("task_ids") == ["publish_final_report"]
            and second.get("contract_revision") == 2
        ),
        "baseline_preserved_in_final_report": bool(
            baseline.get("run_id") == run_id
            and final.get("run_id") == run_id
            and final.get("baseline_sha256") == sha256_file(root / "workspace/artifacts/baseline_report.json")
        ),
        "final_report_cites_injected_requirement": bool(
            final.get("request_id") == request_id
            and criterion_id in final.get("applied_criterion_ids", [])
        ),
        "run_completed": state.get("status") == "completed" and state.get("phase") == 2,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {"run_id": run_id, "passed": not failures, "checks": checks, "failures": failures}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run or independently verify a runtime requirement change")
    parser.add_argument("--evidence-dir", type=Path, default=Path("runs/runtime_change_acceptance"))
    parser.add_argument("--run-id")
    parser.add_argument("--delay-seconds", type=float, default=0.2)
    parser.add_argument("--inject-only", action="store_true")
    parser.add_argument("--framework-run-dir", type=Path)
    parser.add_argument("--injector-log", type=Path)
    parser.add_argument("--baseline-artifact", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args(argv)
    if args.verify:
        result = verify_run(args.verify)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1
    if args.inject_only:
        if not all((args.run_id, args.framework_run_dir, args.injector_log, args.baseline_artifact)):
            parser.error("--inject-only requires run ID, framework run directory, injector log, and baseline artifact")
        return inject_runtime_requirement(
            args.run_id,
            args.framework_run_dir,
            args.injector_log,
            args.baseline_artifact,
            delay_seconds=args.delay_seconds,
        )
    summary = run_experiment(args.evidence_dir, args.run_id, args.delay_seconds)
    print(json.dumps({"run_id": summary["run_id"], "verification_passed": summary["verification_passed"], "summary_path": str((args.evidence_dir.resolve() / summary["run_id"] / "summary.json"))}, ensure_ascii=False, indent=2))
    return 0 if summary["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
