from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator


def software_handler(task, context):

    print("\n[Agent executing]")
    print("Task:", task.description)

    return (
        f"Finished task: {task.description}"
    )


def main():

    registry = AgentRegistry()


    # 软件工程Agent
    registry.register(
        DeterministicAgent(
            role="analyst",
            handler=software_handler
        )
    )

    registry.register(
        DeterministicAgent(
            role="architect",
            handler=software_handler
        )
    )

    registry.register(
        DeterministicAgent(
            role="tester",
            handler=software_handler
        )
    )

    registry.register(
        DeterministicAgent(
            role="developer",
            handler=software_handler
        )
    )

    registry.register(
        DeterministicAgent(
            role="reviewer",
            handler=software_handler
        )
    )


    orchestrator = Orchestrator(
        registry
    )


    agent = MainAgent(
        orchestrator
    )


    goal = """
    Analyze software project,
    find bugs,
    modify code,
    run tests.
    """


    report = agent.execute(goal)


    print("\n========== REPORT ==========")

    print(
        "Status:",
        report.status
    )


    for task_id,result in report.results.items():

        print(
            task_id,
            ":",
            result.summary
        )


if __name__ == "__main__":
    main()
