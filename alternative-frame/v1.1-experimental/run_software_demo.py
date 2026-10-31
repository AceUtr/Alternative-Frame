"""Run the deterministic, offline software engineering demonstration."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.acceptance import AcceptanceEvaluator
from core.artifact_store import publish_run_artifacts, publish_run_evidence
from core.domains import DomainRegistry
from core.local_recovery import LocalDAGRecoveryController
from core.long_horizon import (
    DeterministicGlobalEvaluator,
    LongHorizonController,
    LongHorizonStore,
)
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from domains.software_demo import DEFAULT_GOAL, EXACT_TEST_COMMAND, SoftwareDomainAdapter


ROOT = Path(__file__).resolve().parent
SCENARIOS = ("none", "retry-once", "local-recovery")
MANIFEST_NAME = "run_manifest.json"
REQUIRED_ARTIFACTS = (
    "workspace/artifacts/software_report.md",
    "workspace/artifacts/code_diff.patch",
    "workspace/artifacts/test_log.txt",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(
    run_root: Path,
    scenario: str,
    run_id: str,
    state: dict[str, Any],
    process_exit_code: int,
) -> Path:
    tests = [
        record
        for record in state.get("evidence_records", [])
        if record.get("tool") == "test_runner"
        and record.get("arguments", {}).get("command") == EXACT_TEST_COMMAND
    ]
    test = tests[-1] if tests else {}
    manifest = {
        "schema_version": "1.0",
        "run_id": run_id,
        "scenario": scenario,
        "goal": DEFAULT_GOAL,
        "status": state.get("status"),
        "phase_count": state.get("phase", 0),
        "test_command": EXACT_TEST_COMMAND,
        "test_exit_code": test.get("exit_code"),
        "process_exit_code": process_exit_code,
        "state_file": "state.json",
        "events_file": "events.jsonl",
        "artifacts": list(REQUIRED_ARTIFACTS),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = run_root / MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _event_payloads(run_root: Path) -> list[dict[str, Any]]:
    path = run_root / "events.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_demo(
    *,
    scenario: str = "none",
    workspace: str | Path | None = None,
    runs_dir: str | Path | None = None,
    run_id: str | None = None,
    reset: bool = True,
):
    if scenario not in SCENARIOS:
        raise ValueError(f"unsupported fault scenario: {scenario}")

    chosen_id = run_id or f"{scenario}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}"
    runs_path = Path(runs_dir).resolve() if runs_dir else Path(
        tempfile.mkdtemp(prefix="alternative-frame-software-runs-")
    ).resolve()
    workspace_path = Path(workspace).resolve() if workspace else Path(
        tempfile.mkdtemp(prefix=f"alternative-frame-software-{chosen_id}-")
    ).resolve()

    adapter = SoftwareDomainAdapter()
    if reset:
        adapter.reset_workspace(workspace_path)
    tools, agents = adapter.configure(workspace_path)
    plan = (
        adapter.build_full_plan(DEFAULT_GOAL, scenario)
        if scenario == "local-recovery"
        else adapter.build_plan(DEFAULT_GOAL)
    )
    contract = adapter.build_contract(DEFAULT_GOAL)
    HarnessPreflightChecker().check(
        domains=DomainRegistry([adapter]),
        domain=adapter.name,
        plan=plan,
        agents=agents,
        tools=tools,
        workspace=workspace_path,
        contract=contract,
    ).require_ready()

    store = LongHorizonStore(runs_path)
    def orchestrator_event(event, task, result=None):
        payload = {"task": task.id, "role": task.role}
        if result is not None:
            payload.update(
                {
                    "status": result.status,
                    "attempts": result.attempts,
                    "failures": list(result.failures),
                }
            )
        store.append_event(chosen_id, event, payload)

    orchestrator = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace_path),
        on_event=orchestrator_event,
    )
    local_recovery = (
        LocalDAGRecoveryController(orchestrator, max_cycles=1)
        if scenario == "local-recovery"
        else None
    )

    def evaluator_event(event, payload):
        store.append_event(chosen_id, event, payload)

    def replan(_state, evaluation):
        return adapter.build_recovery_plan(
            DEFAULT_GOAL,
            evaluation.missing_criteria,
            fault_scenario=scenario,
        )

    controller = LongHorizonController(
        orchestrator=orchestrator,
        initial_planner=lambda _state: plan,
        store=store,
        evaluator=DeterministicGlobalEvaluator(
            contract,
            workspace_path,
            on_event=evaluator_event,
        ),
        replanner=replan,
        max_phases=2,
        max_total_tasks=12,
        acceptance_contract=contract.to_dict(),
        local_recovery=local_recovery,
    )
    report = controller.run(DEFAULT_GOAL, run_id=chosen_id)
    run_root = runs_path / chosen_id
    state = _read_json(run_root / "state.json")
    failures = []
    if state.get("status") != "completed":
        failures.append(f"state status is not completed: {state.get('status')}")
    if scenario == "retry-once" and not any(
        event.get("event") == "task_retry_scheduled"
        for event in _event_payloads(run_root)
    ):
        failures.append("missing task retry evidence")
    if scenario == "local-recovery" and not any(
        event.get("event") == "local_recovery_started"
        for event in _event_payloads(run_root)
    ):
        failures.append("missing local recovery evidence")

    process_exit_code = 1 if failures else 0
    _write_manifest(run_root, scenario, chosen_id, state, process_exit_code)
    delivery_artifacts = run_root / "workspace" / "artifacts"
    delivery_artifacts.mkdir(parents=True, exist_ok=True)
    for relative in (
        "software_report.md",
        "code_diff.patch",
        "test_log.txt",
    ):
        source = workspace_path / "artifacts" / relative
        if source.is_file():
            shutil.copy2(source, delivery_artifacts / relative)
    published = publish_run_artifacts(
        workspace_path,
        "software",
        chosen_id,
        (
            "requirements.md",
            "README.md",
            "app.py",
            "test_app.py",
            "artifacts/diagnosis.json",
            "artifacts/software_report.md",
            "artifacts/code_diff.patch",
            "artifacts/test_log.txt",
        ),
        output_root=runs_path / "outputs",
    )
    publish_run_evidence(run_root, published)
    (published / MANIFEST_NAME).write_text(
        (run_root / MANIFEST_NAME).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    report.run_root = run_root
    report.failures = failures
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic software Demo.")
    parser.add_argument("--fault-scenario", choices=SCENARIOS, default="none")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    try:
        report = run_demo(
            scenario=args.fault_scenario,
            workspace=args.workspace,
            runs_dir=args.runs_dir,
            run_id=args.run_id,
        )
        print(f"Status: {report.status}")
        print(f"Phase count: {report.state.phase}")
        print(f"Runtime root: {report.run_root}")
        print(f"Run manifest: {report.run_root / MANIFEST_NAME}")
        for failure in report.failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 0 if report.status == "completed" and not report.failures else 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
