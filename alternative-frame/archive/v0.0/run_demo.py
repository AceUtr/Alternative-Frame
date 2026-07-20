from core.orchestrator import Orchestrator
from core.main_agent import MainAgent
from core.planning import PlanningPipeline
from domains.presets import demo_registry, research_plan, software_plan


def print_report(report):
    print(f"goal={report.goal}")
    print(f"status={report.status} rounds={report.rounds}")
    for task_id, result in report.results.items():
        print(f"  {task_id}: {result.status} attempts={result.attempts} artifacts={result.artifacts}")
    if report.failures:
        print("failures:", report.failures)


if __name__ == "__main__":
    runtime = Orchestrator(demo_registry(), max_workers=3)
    main_agent = MainAgent(runtime, PlanningPipeline().build)
    print("[research]")
    print_report(main_agent.execute("research experiment"))
    print("\n[software engineering]")
    print_report(main_agent.execute("software delivery"))
