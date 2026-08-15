"""Run the first-stage reproducible offline research baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from core.acceptance import AcceptanceEvaluator
from core.domains import DomainRegistry
from core.local_recovery import LocalDAGRecoveryController
from core.long_horizon import (
    DeterministicGlobalEvaluator,
    LongHorizonController,
    LongHorizonStore,
)
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from domains.research_demo import BASELINE_COMMAND, ResearchDomainAdapter
from domains.research_demo import ResearchGlobalEvaluator


GOAL = (
    "Run a reproducible baseline and improved experiment, independently verify "
    "metrics, and produce a report"
)
FAULT_SCENARIOS = ("normal", "task-retry", "local-recovery")


def run_demo(
    workspace: Path,
    runs_dir: Path,
    run_id: str,
    fault_scenario: str = "normal",
    on_task_event=None,
    on_long_event=None,
    on_global_event=None,
    on_controller_ready=None,
    on_plan_ready=None,
    on_preflight=None,
    contract_override=None,
):
    if fault_scenario not in FAULT_SCENARIOS:
        raise ValueError(f"unsupported fault scenario: {fault_scenario}")
    adapter = ResearchDomainAdapter()
    adapter.reset_workspace(workspace)
    domains = DomainRegistry([adapter])
    tools, agents = adapter.configure(workspace, model_client=None)
    initial_plan = adapter.build_plan(GOAL)
    if fault_scenario == "task-retry":
        baseline_task = initial_plan.task_map()["run_baseline"]
        baseline_task.metadata["fault_injection"] = {
            "enabled": True,
            "id": "demo-baseline-parameter-repair",
            "mode": "argument_override",
            "fail_attempts": 1,
            "argument_overrides": {
                "command": (
                    "python run_baseline.py --dataset data/dataset.json "
                    "--output artifacts/fault_baseline_metrics.json"
                ),
            },
        }
        baseline_task.metadata["retry_repair"] = {
            "feedback_category": "missing_artifact",
            "cleanup_paths": ["artifacts/fault_baseline_metrics.json"],
            "arguments": {
                "command": BASELINE_COMMAND,
            },
        }
    elif fault_scenario == "local-recovery":
        improved_task = initial_plan.task_map()["run_improved"]
        improved_task.max_retries = 0
        improved_task.metadata["fault_injection"] = {
            "enabled": True,
            "id": "demo-improved-local-recovery",
            "mode": "transient_failure",
            "fail_attempts": 1,
        }
    contract = contract_override or adapter.build_contract(GOAL)
    if on_plan_ready:
        on_plan_ready(initial_plan, contract)

    preflight = HarnessPreflightChecker().check(
        domains=domains,
        domain=adapter.name,
        plan=initial_plan,
        agents=agents,
        tools=tools,
        workspace=workspace,
        contract=contract,
    )
    if on_preflight:
        on_preflight(preflight)
    preflight.require_ready()
    store = LongHorizonStore(runs_dir)

    def record_task_event(event, task, result=None):
        payload = {
            "task_id": task.id,
            "attempt": task.metadata.get("runtime_attempt"),
        }
        if result is not None:
            payload["status"] = result.status
            payload["failures"] = list(result.failures)
        store.append_event(run_id, event, payload)
        if on_task_event:
            on_task_event(event, task, result)

    orchestrator = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
        on_event=record_task_event,
    )

    def replan(_state, evaluation):
        verification_gaps = {"verification_metrics", "verification_command"}
        if verification_gaps.intersection(evaluation.missing_criteria):
            return adapter.build_recovery_plan(GOAL)
        return None

    def record_global_event(event, payload):
        store.append_event(run_id, event, payload)
        if on_global_event:
            on_global_event(event, payload)

    controller = LongHorizonController(
        orchestrator,
        initial_planner=lambda _state: initial_plan,
        store=store,
        evaluator=ResearchGlobalEvaluator(
            contract, workspace, on_event=record_global_event
        ),
        replanner=replan,
        local_recovery=LocalDAGRecoveryController(orchestrator, max_cycles=1),
        max_phases=2,
        max_total_tasks=12,
        acceptance_contract=contract.to_dict(),
        on_event=on_long_event,
    )
    if on_controller_ready:
        on_controller_ready(controller)
    return controller.run(GOAL, run_id=run_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fault-scenario",
        choices=FAULT_SCENARIOS,
        default="normal",
        help="Run the normal demo or one controlled recovery scenario.",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent
    workspace = project_root / "examples" / "research_task"
    run_id = "research_" + uuid4().hex[:8]
    report = run_demo(
        workspace,
        project_root / "runs" / "research",
        run_id,
        fault_scenario=args.fault_scenario,
    )
    metrics_path = workspace / "artifacts" / "baseline_metrics.json"
    print("domain=research")
    print(f"run_id={run_id}")
    print(f"status={report.status}")
    print(f"phases={report.state.phase}")
    print(f"tasks={report.state.total_tasks}")
    print(f"fault_scenario={args.fault_scenario}")
    print(
        "local_recovery_cycles="
        f"{sum(phase.local_recovery_cycles for phase in report.state.phases)}"
    )
    print(f"metrics={metrics_path.relative_to(project_root).as_posix()}")
    if args.fault_scenario == "task-retry":
        baseline = report.phase_reports[0].results.get("run_baseline")
        feedback = [
            item.split("=", 1)[1]
            for item in (baseline.evidence if baseline else [])
            if item.startswith("retry_feedback_applied=")
        ]
        print(f"attempts={baseline.attempts if baseline else 0}")
        print(f"retry_feedback={feedback[-1] if feedback else 'missing'}")
        print(
            "error_artifact_cleaned="
            f"{not (workspace / 'artifacts/fault_baseline_metrics.json').exists()}"
        )
    if args.fault_scenario == "local-recovery":
        events_path = project_root / "runs" / "research" / run_id / "events.jsonl"
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
        ]
        started = next(
            item["payload"]
            for item in events
            if item["event"] == "local_recovery_started"
        )
        planned = next(
            item["payload"]
            for item in events
            if item["event"] == "local_recovery_planned"
        )
        print(f"frozen_nodes={','.join(started.get('frozen', []))}")
        print(
            "rebuilt_nodes="
            + ",".join(task.get("id", "") for task in planned.get("tasks", []))
        )
    if report.status != "completed" or report.state.phase != 2:
        print(f"failure={report.state.last_error or 'two-phase contract not completed'}")
        return 1
    first = report.state.phases[0].evaluation
    if "verification_metrics" not in first.get("missing_criteria", []):
        print("failure=phase one did not expose the verification evidence gap")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
