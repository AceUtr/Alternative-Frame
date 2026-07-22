from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator


def software_handler(task, context):
    print(f"Executing: {task.description}")

    return (
        f"Completed software engineering task: "
        f"{task.description}"
    )


def main():

    # 注册 Agent
    registry = AgentRegistry()

    software_agent = DeterministicAgent(
        role="software_engineer",
        handler=software_handler
    )

    registry.register(software_agent)


    # 创建 Orchestrator
    orchestrator = Orchestrator(
        registry=registry
    )


    # 创建 MainAgent
    agent = MainAgent(
        orchestrator=orchestrator
    )


    # 输入软件工程任务
    goal = """
    Analyze calculator project,
    find bugs,
    modify code,
    run tests.
    """


    report = agent.execute(goal)


    print("\n===== Result =====")

    print("Status:",
          report.status)

    for task_id, result in report.results.items():

        print("\nTask:",
              task_id)

        print(result.summary)



if __name__ == "__main__":
    main()
