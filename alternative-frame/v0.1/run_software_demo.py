from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from core.acceptance import AcceptanceEvaluator
from core.domains import DomainRegistry
from core.local_recovery import LocalDAGRecoveryController
from core.long_horizon import LongHorizonController, LongHorizonStore
from core.long_horizon.global_evaluator import DeterministicGlobalEvaluator
from core.main_agent import MainAgent
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from domains.software_demo import SoftwareDomainAdapter


GOAL = "Repair the supplied buggy application and prove the exact test command passes"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the software engineering demo.")
    parser.add_argument(
        "--single-phase",
        action="store_true",
        help="Run the one-phase smoke DAG used for local debugging.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional long-horizon run id. Defaults to a timestamped software-demo id.",
    )
    parser.add_argument(
        "--fault-scenario",
        choices=("none", "local-recovery"),
        default="none",
        help="Optional controlled fault injection scenario for recovery demonstrations.",
    )
    return parser.parse_args(argv)


def configure(root: Path):
    workspace = root / "examples" / "software_task"
    adapter = SoftwareDomainAdapter()
    adapter.reset_workspace(workspace)
    tools, agents = adapter.configure(workspace=workspace)
    contract = adapter.build_contract(GOAL)
    return adapter, workspace, tools, agents, contract


def run_preflight(adapter, workspace, tools, agents, plan, contract):
    report = HarnessPreflightChecker().check(
        domains=DomainRegistry([adapter]),
        domain=adapter.name,
        plan=plan,
        agents=agents,
        tools=tools,
        workspace=workspace,
        contract=contract,
    )
    report.require_ready()


def build_orchestrator(agents, tools, workspace):
    return Orchestrator(
        registry=agents,
        acceptance=AcceptanceEvaluator(workspace),
        tools=tools,
    )


def run_single_phase(root: Path) -> int:
    adapter, workspace, tools, agents, contract = configure(root)
    plan = adapter.build_plan(GOAL)
    run_preflight(adapter, workspace, tools, agents, plan, contract)

    orchestrator = build_orchestrator(agents, tools, workspace)
    report = MainAgent(orchestrator, planner=adapter.build_plan).execute(GOAL)

    print("\n========== SOFTWARE DEMO REPORT ==========")
    print("Mode: single-phase smoke")
    print("Status:", report.status)
    print("Rounds:", report.rounds)
    print_task_report(report)
    print("\nReport artifact:", workspace / "artifacts" / "software_report.md")
    return 0 if report.status == "success" else 1


def apply_fault_scenario(plan, scenario: str):
    if scenario == "local-recovery":
        for task in plan.subtasks:
            if task.id == "run_targeted_tests":
                task.metadata["fault_scenario"] = "local-recovery"
    return plan


def run_two_phase(root: Path, run_id: str | None = None, fault_scenario: str = "none") -> int:
    adapter, workspace, tools, agents, contract = configure(root)
    if fault_scenario == "local-recovery":
        initial_plan = apply_fault_scenario(adapter.build_plan(GOAL), fault_scenario)
    else:
        initial_plan = adapter.build_initial_plan(GOAL)
    run_preflight(adapter, workspace, tools, agents, initial_plan, contract)

    orchestrator = build_orchestrator(agents, tools, workspace)
    evaluator = DeterministicGlobalEvaluator(contract, workspace)
    store = LongHorizonStore(root / "runs" / "long_horizon")
    actual_run_id = run_id or f"software-demo-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    def initial_planner(_state):
        if fault_scenario == "local-recovery":
            return apply_fault_scenario(adapter.build_plan(GOAL), fault_scenario)
        return adapter.build_initial_plan(GOAL)

    def replanner(_state, evaluation):
        return adapter.build_recovery_plan(GOAL, evaluation.missing_criteria)

    controller = LongHorizonController(
        orchestrator,
        initial_planner=initial_planner,
        store=store,
        evaluator=evaluator,
        replanner=replanner,
        max_phases=2,
        max_total_tasks=16,
        acceptance_contract=contract.to_dict(),
        local_recovery=(
            LocalDAGRecoveryController(orchestrator, max_cycles=1)
            if fault_scenario == "local-recovery"
            else None
        ),
    )
    report = controller.run(GOAL, run_id=actual_run_id)

    print("\n========== SOFTWARE LONG-HORIZON DEMO REPORT ==========")
    print("Mode: two-phase long-horizon")
    print("Fault scenario:", fault_scenario)
    print("Status:", report.status)
    print("Run id:", report.state.run_id)
    print("Phase count:", report.state.phase)
    for phase, phase_report in zip(report.state.phases, report.phase_reports):
        print(f"\n[phase {phase.number}] report={phase.report_status} state={phase.status}")
        print("Tasks:", ", ".join(phase.task_ids))
        print("Local recovery cycles:", phase.local_recovery_cycles)
        print("Executed task count:", phase.executed_task_count)
        print("Missing criteria:", ", ".join(phase.evaluation.get("missing_criteria", [])) or "none")
        print_task_report(phase_report)

    run_dir = store.run_dir(report.state.run_id)
    print("\nState:", run_dir / "state.json")
    print("Events:", run_dir / "events.jsonl")
    print("Report artifact:", workspace / "artifacts" / "software_report.md")
    return 0 if report.status == "completed" else 1


def print_task_report(report):
    for task_id, result in report.results.items():
        print(f"\n[{task_id}] {result.status} attempts={result.attempts}")
        print(result.summary)
        if result.failures:
            print("Failures:")
            for failure in result.failures:
                print(" -", str(failure).splitlines()[0])
        if result.artifacts:
            print("Artifacts:")
            for artifact in result.artifacts:
                print(" -", artifact)


def main(argv=None) -> int:
    args = parse_args(argv)
    root = Path(__file__).resolve().parent
    if args.single_phase:
        return run_single_phase(root)
    return run_two_phase(root, args.run_id, args.fault_scenario)


if __name__ == "__main__":
    raise SystemExit(main())
