from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator
from domains.software_demo import build

import os


def software_handler(task, context):

    print("\n[Agent executing]")
    print("Role:", task.role)
    print("Task:", task.description)


    project="examples/software_task"

    app_file=f"{project}/app.py"


    # ====================
    # Analyst
    # ====================

    if task.role=="analyst":


        if os.path.exists(app_file):

            with open(
                app_file,
                "r",
                encoding="utf8"
            ) as f:

                code=f.read()


            print("\nCurrent Code:")
            print(code)


            if "-" in code:

                return "Found bug: add function uses subtraction"

            else:

                return "No obvious bug found"


        else:

            return "app.py not found"



    # ====================
    # Developer
    # ====================

    elif task.role=="developer":


        os.makedirs(
            project,
            exist_ok=True
        )


        with open(
            app_file,
            "w",
            encoding="utf8"
        ) as f:


            f.write(
"""
def add(a,b):
    return a+b
"""
            )


        print(
            "Developer fixed app.py"
        )


        return "Code modification completed"



    # ====================
    # Tester
    # ====================

    elif task.role=="tester":


        import subprocess


        result=subprocess.run(
            [
                "pytest",
                project
            ],
            capture_output=True,
            text=True
        )


        print(result.stdout)


        if result.returncode==0:

            return "All tests passed"

        else:

            return "Tests failed"



    # ====================
    # Other Agents
    # ====================

    else:

        return (
            f"Finished {task.description}"
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
