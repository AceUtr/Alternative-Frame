"""Run the first-stage reproducible offline research baseline."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from core.acceptance import AcceptanceEvaluator
from core.domains import DomainRegistry
from core.long_horizon import (
    DeterministicGlobalEvaluator,
    LongHorizonController,
    LongHorizonStore,
)
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from domains.research_demo import ResearchDomainAdapter


GOAL = (
    "Run a reproducible baseline and improved experiment, independently verify "
    "metrics, and produce a report"
)


def run_demo(workspace: Path, runs_dir: Path, run_id: str):
    adapter = ResearchDomainAdapter()
    adapter.reset_workspace(workspace)
    domains = DomainRegistry([adapter])
    tools, agents = adapter.configure(workspace, model_client=None)
    initial_plan = adapter.build_plan(GOAL)
    contract = adapter.build_contract(GOAL)

    preflight = HarnessPreflightChecker().check(
        domains=domains,
        domain=adapter.name,
        plan=initial_plan,
        agents=agents,
        tools=tools,
        workspace=workspace,
        contract=contract,
    )
    preflight.require_ready()
    orchestrator = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
    )

    def replan(_state, evaluation):
        verification_gaps = {"verification_metrics", "verification_command"}
        if verification_gaps.intersection(evaluation.missing_criteria):
            return adapter.build_recovery_plan(GOAL)
        return None

    controller = LongHorizonController(
        orchestrator,
        initial_planner=lambda _state: initial_plan,
        store=LongHorizonStore(runs_dir),
        evaluator=DeterministicGlobalEvaluator(contract, workspace),
        replanner=replan,
        max_phases=2,
        max_total_tasks=12,
        acceptance_contract=contract.to_dict(),
    )
    return controller.run(GOAL, run_id=run_id)


def main() -> int:
    project_root = Path(__file__).resolve().parent
    workspace = project_root / "examples" / "research_task"
    run_id = "research_" + uuid4().hex[:8]
    report = run_demo(workspace, project_root / "runs" / "research", run_id)
    metrics_path = workspace / "artifacts" / "baseline_metrics.json"
    print("domain=research")
    print(f"run_id={run_id}")
    print(f"status={report.status}")
    print(f"phases={report.state.phase}")
    print(f"metrics={metrics_path.relative_to(project_root).as_posix()}")
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
