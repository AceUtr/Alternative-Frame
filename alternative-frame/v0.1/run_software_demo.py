"""Run the deterministic, offline software engineering demonstration."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from core.acceptance import AcceptanceEvaluator
from core.long_horizon import (
    DeterministicGlobalEvaluator,
    LongHorizonController,
    LongHorizonStore,
)
from core.local_recovery import LocalDAGRecoveryController
from core.orchestrator import Orchestrator
from domains.software_demo import SoftwareDomainAdapter


GOAL = "Repair the supplied buggy application and prove the exact test command passes"
SCENARIOS = ("none", "retry-once", "local-recovery")


def _runtime_root(scenario: str, state_dir: str | None) -> Path:
    base = Path(state_dir).resolve() if state_dir else Path(tempfile.gettempdir()) / "alternative-frame-software-demo"
    run_id = f"{scenario}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}"
    return base / run_id


def build_controller(scenario: str, state_dir: str | None = None):
    adapter = SoftwareDomainAdapter()
    runtime_root = _runtime_root(scenario, state_dir)
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
        for task in plan.subtasks:
            if task.id == "implement_fix" and scenario == "retry-once":
                task.metadata["fault_scenario"] = scenario

    contract = adapter.build_contract(GOAL)
    task_events: list[tuple[str, str, object | None]] = []

    def on_task_event(event, task, result=None):
        task_events.append((event, task.id, result))

    orchestrator = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
        on_event=on_task_event,
    )
    local_recovery = (
        LocalDAGRecoveryController(orchestrator, max_cycles=1)
        if scenario == "local-recovery"
        else None
    )

    def replan(_state, evaluation):
        return adapter.build_recovery_plan(GOAL, evaluation.missing_criteria)

    controller = LongHorizonController(
        orchestrator=orchestrator,
        initial_planner=lambda _state: plan,
        store=LongHorizonStore(runtime_root / "runs"),
        evaluator=DeterministicGlobalEvaluator(contract, workspace),
        replanner=replan,
        max_phases=2,
        max_total_tasks=16,
        acceptance_contract=contract.to_dict(),
        local_recovery=local_recovery,
    )
    return controller, runtime_root, task_events


def _read_events(runtime_root: Path) -> list[dict]:
    event_files = list((runtime_root / "runs").glob("*/*events.jsonl"))
    if not event_files:
        return []
    return [
        json.loads(line)
        for line in event_files[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_demo(scenario: str, state_dir: str | None = None) -> int:
    controller, runtime_root, task_events = build_controller(scenario, state_dir)
    report = controller.run(GOAL, run_id="software-demo", resume=False)
    state = report.state

    print(f"Status: {state.status}")
    print(f"Phase count: {state.phase}")
    print(f"Runtime root: {runtime_root}")

    if scenario == "retry-once":
        result = report.phase_reports[0].results["implement_fix"]
        feedback = [
            record
            for record in result.tool_records
            if record.get("tool") == "retry_feedback"
        ]
        print(f"implement_fix attempts={result.attempts}")
        print(f"structured retry_feedback={feedback[0]['arguments'] if feedback else None}")
        if result.attempts != 2 or not feedback:
            return 1

    if scenario == "local-recovery":
        events = _read_events(runtime_root)
        recovery = next(
            (
                event["payload"]
                for event in events
                if event["event"] == "local_recovery_started"
            ),
            None,
        )
        print(f"local recovery={recovery}")
        if not recovery or not recovery.get("frozen") or not recovery.get("impacted"):
            return 1

    if state.status != "completed":
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault-scenario", choices=SCENARIOS, default="none")
    parser.add_argument("--state-dir", help="Optional directory for temporary run state and evidence.")
    args = parser.parse_args(argv)
    return run_demo(args.fault_scenario, args.state_dir)


if __name__ == "__main__":
    raise SystemExit(main())
