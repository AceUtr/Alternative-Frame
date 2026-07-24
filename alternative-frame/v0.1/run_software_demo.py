from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator
from domains.software_demo import build

import os


def software_handler(task, context):

    print("\n[Agent executing]")
    print("Role:", task.role)
    print("Task:", task.description)


    if task.role=="analyst":

        path="examples/software_task/app.py"

        if os.path.exists(path):

            with open(path,"r",encoding="utf8") as f:
                code=f.read()

            print("\nCode analysis:")
            print(code)

            return "Found possible bug in add function"


    elif task.role=="developer":

        path="examples/software_task/app.py"

        with open(path,"w",encoding="utf8") as f:

            f.write(
"""
def add(a,b):
    return a+b
"""
            )

        return "Bug fixed"


    elif task.role=="tester":

        return "pytest executed"


    else:

        return f"Finished {task.description}"


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
        registry=registry
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
