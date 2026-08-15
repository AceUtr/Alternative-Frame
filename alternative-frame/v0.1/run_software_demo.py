"""Run the deterministic, offline software engineering demonstration."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.acceptance import AcceptanceEvaluator
from core.local_recovery import LocalDAGRecoveryController
from core.long_horizon import (
    DeterministicGlobalEvaluator,
    LongHorizonController,
    LongHorizonStore,
)
from core.orchestrator import Orchestrator
from domains.software_demo import SoftwareDomainAdapter


GOAL = "Repair the supplied buggy application and prove the exact test command passes"
SCENARIOS = ("none", "retry-once", "local-recovery")
REQUIRED_ARTIFACTS = (
    "workspace/artifacts/software_report.md",
    "workspace/artifacts/code_diff.patch",
    "workspace/artifacts/test_log.txt",
)


def _new_run_id(scenario: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return f"{scenario}-{stamp}"


def _runtime_base(state_dir: str | None) -> Path:
    if state_dir:
        return Path(state_dir).resolve()
    return Path(tempfile.gettempdir()).resolve() / "alternative-frame-software-demo"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_events(runtime_root: Path) -> list[dict[str, Any]]:
    events_path = runtime_root / "events.jsonl"
    if not events_path.is_file():
        return []
    return [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _task_attempts(state: dict[str, Any], task_id: str) -> int:
    attempts = 0
    for phase in state.get("phases", []):
        for record in phase.get("tasks", []):
            if record.get("id") == task_id:
                attempts = max(attempts, int(record.get("attempts", 0)))
    if attempts:
        return attempts

    # LongHorizonState persists tool evidence, but its PhaseRecord intentionally
    # stores summary metadata rather than each AgentResult. Retry feedback carries
    # the next attempt number, so it is the durable source for this CLI evidence.
    for record in state.get("evidence_records", []):
        if record.get("tool") != "retry_feedback":
            continue
        arguments = record.get("arguments")
        if isinstance(arguments, dict):
            attempts = max(attempts, int(arguments.get("attempt", 0)))
    if attempts:
        return attempts

    for completed in state.get("completed_tasks", []):
        if str(completed).endswith(f":{task_id}"):
            attempts = max(attempts, 1)
    return attempts


def _find_retry_feedback(state: dict[str, Any]) -> list[dict[str, Any]]:
    feedback = []
    for record in state.get("evidence_records", []):
        if record.get("tool") == "retry_feedback":
            feedback.append(record)
    return feedback


def _find_retry_summary(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events:
        if event.get("event") == "retry_summary":
            payload = event.get("payload")
            if isinstance(payload, dict):
                return payload
    return None


def _record_retry_summary(
    controller: LongHorizonController,
    run_id: str,
    attempts: int,
    feedback: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if _find_retry_summary(events) or not feedback:
        return events

    controller.store.append_event(
        run_id,
        "retry_summary",
        {
            "task": "implement_fix",
            "attempts": attempts,
            "retry_feedback": feedback,
        },
    )
    return _read_events(controller.store.run_dir(run_id))


def _find_local_recovery(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events:
        if event.get("event") == "local_recovery_started":
            payload = event.get("payload")
            if isinstance(payload, dict):
                return payload
    return None


def _validate_common_artifacts(runtime_root: Path) -> list[str]:
    failures = []

    state_path = runtime_root / "state.json"
    events_path = runtime_root / "events.jsonl"

    if not runtime_root.is_dir():
        failures.append(f"runtime root does not exist: {runtime_root}")
    if not state_path.is_file():
        failures.append(f"missing state.json: {state_path}")
    if not events_path.is_file():
        failures.append(f"missing events.jsonl: {events_path}")

    for artifact in REQUIRED_ARTIFACTS:
        path = runtime_root / artifact
        if not path.is_file():
            failures.append(f"missing artifact: {path}")

    if state_path.is_file():
        state = _read_json(state_path)
        if state.get("status") != "completed":
            failures.append(f"state status is not completed: {state.get('status')}")
        if int(state.get("phase", 0)) < 1:
            failures.append("phase count is not positive")
        if not state.get("completed_tasks"):
            failures.append("state has no completed_tasks")
        if "last_evaluation" not in state:
            failures.append("state has no acceptance evaluation")

    return failures


def _build_controller(scenario: str, runtime_base: Path, run_id: str):
    adapter = SoftwareDomainAdapter()
    runtime_root = runtime_base / run_id
    workspace = runtime_root / "workspace"
    adapter.reset_workspace(workspace)
    tools, agents = adapter.configure(workspace, model_client=None)

    if scenario == "local-recovery":
        plan = adapter.build_plan(GOAL)
        for task in plan.subtasks:
            if task.id == "run_targeted_tests":
                task.metadata["fault_scenario"] = scenario
    else:
        plan = adapter.build_initial_plan(GOAL)
        if scenario == "retry-once":
            for task in plan.subtasks:
                if task.id == "implement_fix":
                    task.metadata["fault_scenario"] = scenario

    contract = adapter.build_contract(GOAL)

    orchestrator = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
    )

    local_recovery = None
    if scenario == "local-recovery":
        local_recovery = LocalDAGRecoveryController(orchestrator, max_cycles=1)

    def replan(_state, evaluation):
        return adapter.build_recovery_plan(GOAL, evaluation.missing_criteria)

    controller = LongHorizonController(
        orchestrator=orchestrator,
        initial_planner=lambda _state: plan,
        store=LongHorizonStore(runtime_base),
        evaluator=DeterministicGlobalEvaluator(contract, workspace),
        replanner=replan,
        max_phases=2,
        max_total_tasks=16,
        acceptance_contract=contract.to_dict(),
        local_recovery=local_recovery,
    )
    return controller, runtime_root


def run_demo(scenario: str, state_dir: str | None = None) -> int:
    runtime_base = _runtime_base(state_dir)
    run_id = _new_run_id(scenario)
    controller, runtime_root = _build_controller(scenario, runtime_base, run_id)

    report = controller.run(GOAL, run_id=run_id, resume=False)
    state_path = runtime_root / "state.json"
    state = _read_json(state_path) if state_path.is_file() else report.state.to_dict()
    events = _read_events(runtime_root)

    print(f"Status: {report.state.status}")
    print(f"Phase count: {report.state.phase}")
    print(f"Runtime root: {runtime_root}")

    failures = _validate_common_artifacts(runtime_root)

    if scenario == "retry-once":
        attempts = _task_attempts(state, "implement_fix")
        feedback = _find_retry_feedback(state)
        events = _record_retry_summary(
            controller,
            run_id,
            attempts,
            feedback,
            events,
        )
        print(f"implement_fix attempts={attempts}")
        print(f"structured retry_feedback={feedback[0] if feedback else None}")
        if attempts != 2:
            failures.append(f"expected implement_fix attempts=2, got {attempts}")
        if not feedback:
            failures.append("missing structured retry_feedback evidence")

    if scenario == "local-recovery":
        recovery = _find_local_recovery(events)
        print(f"local recovery={recovery}")
        if not recovery:
            failures.append("missing local recovery event")
        else:
            if not recovery.get("frozen"):
                failures.append("local recovery event has no frozen nodes")
            if not recovery.get("impacted"):
                failures.append("local recovery event has no impacted nodes")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic software engineering demo."
    )
    parser.add_argument(
        "--fault-scenario",
        choices=SCENARIOS,
        default="none",
        help="Controlled fault scenario to demonstrate.",
    )
    parser.add_argument(
        "--state-dir",
        help="Optional parent directory for independent runtime roots.",
    )
    args = parser.parse_args(argv)

    try:
        return run_demo(args.fault_scenario, args.state_dir)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
