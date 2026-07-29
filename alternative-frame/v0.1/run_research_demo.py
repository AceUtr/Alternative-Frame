"""Run the first-stage reproducible offline research baseline."""

from __future__ import annotations

from pathlib import Path

from core.acceptance import AcceptanceEvaluator
from core.domains import DomainRegistry
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from domains.research_demo import ResearchDomainAdapter


GOAL = "Run the reproducible first-stage offline research baseline"


def main() -> int:
    project_root = Path(__file__).resolve().parent
    workspace = project_root / "examples" / "research_task"
    adapter = ResearchDomainAdapter()
    adapter.reset_workspace(workspace)
    domains = DomainRegistry([adapter])
    tools, agents = adapter.configure(workspace, model_client=None)
    plan = adapter.build_plan(GOAL)
    contract = adapter.build_contract(GOAL)

    preflight = HarnessPreflightChecker().check(
        domains=domains,
        domain=adapter.name,
        plan=plan,
        agents=agents,
        tools=tools,
        workspace=workspace,
        contract=contract,
    )
    preflight.require_ready()
    report = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
    ).run(plan, parallel=False)

    metrics_path = workspace / "artifacts" / "baseline_metrics.json"
    print(f"domain={adapter.name}")
    print(f"status={report.status}")
    print(f"tasks={len(report.results)}")
    print(f"metrics={metrics_path.relative_to(project_root).as_posix()}")
    if report.status != "success" or not metrics_path.is_file():
        for failure in report.failures:
            print(f"failure={failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
