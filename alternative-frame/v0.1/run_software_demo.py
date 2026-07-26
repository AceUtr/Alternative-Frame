from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator
from domains.software_demo import build

import os
import subprocess



def software_handler(task, context):

    print("\n[Agent executing]")
    print("Role:", task.role)
    print("Task:", task.description)


    project = "examples/software_task"

    app_file = f"{project}/app.py"



    # =====================
    # Analyst
    # =====================

    if task.role == "analyst":


        if not os.path.exists(app_file):

            return "app.py not found"


        with open(
            app_file,
            "r",
            encoding="utf8"
        ) as f:

            code = f.read()


        print("\nCurrent Code:")
        print(code)


        if "-" in code:

            return "Found bug: add function uses subtraction"


        return "No obvious bug"



    # =====================
    # Developer
    # =====================

    elif task.role == "developer":


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



    # =====================
    # Tester
    # =====================

    elif task.role == "tester":


        print("Running tests...")


        test_file = f"{project}/test_app.py"


        result = subprocess.run(
            [
                "pytest",
                test_file,
                "-v"
            ],
            capture_output=True,
            text=True
        )


        print("\nPytest output:")
        print(result.stdout)



        if result.returncode == 0:

            return "All tests passed"


        else:

            return "Tests failed"



    return "Finished"



def main():



    registry = AgentRegistry()



    registry.register(
        DeterministicAgent(
            role="analyst",
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
            role="tester",
            handler=software_handler
        )
    )



    orchestrator = Orchestrator(
        registry=registry
    )



    agent = MainAgent(
        orchestrator,
        planner=build
    )



    goal = """
    Analyze software project,
    locate bugs,
    modify source code,
    run regression tests.
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
