from __future__ import annotations

import argparse
import tempfile
from datetime import datetime
from pathlib import Path

from core.domains import DomainRegistry
from core.long_horizon import DeterministicGlobalEvaluator, LongHorizonController, LongHorizonStore
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from domains.software_demo import DEFAULT_GOAL, SoftwareDomainAdapter


ROOT = Path(__file__).resolve().parent


def run_demo(*, workspace: str | Path | None = None, runs_dir: str | Path | None = None,
             run_id: str | None = None, reset: bool = True, on_event=None):
    chosen_id = run_id or f"software-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
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
    initial_plan = adapter.build_plan(DEFAULT_GOAL)
    contract = adapter.build_contract(DEFAULT_GOAL)
    HarnessPreflightChecker().check(
        domains=DomainRegistry([adapter]), domain=adapter.name, plan=initial_plan,
        agents=agents, tools=tools, workspace=workspace_path, contract=contract,
    ).require_ready()

    store = LongHorizonStore(runs_path)

    def evaluator_event(event, payload):
        store.append_event(chosen_id, event, payload)
        if on_event:
            on_event(event, payload)

    evaluator = DeterministicGlobalEvaluator(contract, workspace_path, on_event=evaluator_event)
    controller = LongHorizonController(
        Orchestrator(agents), lambda _state: initial_plan, store,
        evaluator=evaluator,
        replanner=lambda _state, evaluation: adapter.build_recovery_plan(DEFAULT_GOAL, evaluation.missing_criteria),
        max_phases=2, max_total_tasks=8, acceptance_contract=contract.to_dict(), on_event=on_event,
    )
    return controller.run(DEFAULT_GOAL, run_id=chosen_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic two-phase software Demo")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    report = run_demo(workspace=args.workspace, runs_dir=args.runs_dir, run_id=args.run_id)
    print(f"status={report.status}")
    print(f"run_id={report.state.run_id}")
    print(f"phases={report.state.phase}")
    print(f"tasks={report.state.total_tasks}")
    print(f"artifacts={','.join(report.state.artifacts)}")
    return 0 if report.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
