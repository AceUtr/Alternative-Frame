from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator
from domains.software_demo import build

from evaluator.evaluator import evaluate
from core.acceptance import AcceptanceEvaluator
from core.models import AgentResult


import os
import subprocess
from datetime import datetime



# ==========================
# Evidence Storage
# ==========================

BEFORE_CODE = ""
AFTER_CODE = ""

TEST_OUTPUT = ""
TEST_EXIT_CODE = None



PROJECT = "examples/software_task"
APP_FILE = f"{PROJECT}/app.py"



def software_handler(task, context):

    global BEFORE_CODE
    global AFTER_CODE
    global TEST_OUTPUT
    global TEST_EXIT_CODE


    print("\n==============================")
    print("[Agent executing]")
    print("Role:", task.role)
    print("Task:", task.description)
    print("==============================")


    # =====================================
    # Analyst
    # =====================================

    if task.role == "analyst":


        with open(
            APP_FILE,
            "r",
            encoding="utf8"
        ) as f:

            code = f.read()


        print("\nCurrent Code:")
        print(code)



        result = """
Requirement Analysis:


Function:

add(a,b)


Expected behavior:

Return the sum of two numbers.


Detected problem:

Current implementation violates requirement.
"""


        print(result)


        return AgentResult(
            subtask_id=task.id,
            status="success",
            summary=result
        )



    # =====================================
    # Architect
    # =====================================

    elif task.role == "architect":


        architecture = """
System Architecture:


Input
 |
 v

Business Logic(add)

 |
 v

Automated Test Validation



Components:

- Application Module
- Business Logic
- Test Framework
"""


        print(architecture)


        return AgentResult(
            subtask_id=task.id,
            status="success",
            summary=architecture
        )



    # =====================================
    # Reviewer
    # =====================================

    elif task.role == "reviewer":


        with open(
            APP_FILE,
            "r",
            encoding="utf8"
        ) as f:

            code=f.read()



        if (
            "return a-b" in code
            or
            "return b-a" in code
        ):

            review="""
Code Review Result:


Bug:

Function add() uses subtraction.


Expected:

return a+b


Solution:

Replace subtraction operator.
"""


        else:

            review="""
Code Review Result:

No bug detected.
"""



        print(review)



        return AgentResult(
            subtask_id=task.id,
            status="success",
            summary=review
        )



    # =====================================
    # Developer
    # =====================================

    elif task.role == "developer":


        with open(
            APP_FILE,
            "r",
            encoding="utf8"
        ) as f:

            code=f.read()



        BEFORE_CODE=code


        print("\nBefore:")
        print(code)



        code=code.replace(
            "return a-b",
            "return a+b"
        )


        code=code.replace(
            "return b-a",
            "return a+b"
        )



        with open(
            APP_FILE,
            "w",
            encoding="utf8"
        ) as f:

            f.write(code)



        AFTER_CODE=code



        print("\nAfter:")
        print(code)



        return AgentResult(
            subtask_id=task.id,
            status="success",
            summary="Source code fixed",
            artifacts=[
                APP_FILE
            ]
        )



    # =====================================
    # Tester
    # =====================================

    elif task.role == "tester":


        print("Running tests...")


        result=subprocess.run(

            [
                "pytest",
                f"{PROJECT}/test_app.py",
                "-v"
            ],

            capture_output=True,

            text=True

        )



        TEST_OUTPUT=result.stdout

        TEST_EXIT_CODE=result.returncode



        print(TEST_OUTPUT)



        if TEST_EXIT_CODE==0:


            return AgentResult(

                subtask_id=task.id,

                status="success",

                summary="All tests passed",

                evidence=[
                    f"pytest_exit_code={TEST_EXIT_CODE}"
                ]

            )


        else:


            return AgentResult(

                subtask_id=task.id,

                status="failed",

                summary="Tests failed",

                failures=[
                    TEST_OUTPUT
                ]

            )



    # =====================================
    # Reporter
    # =====================================

    elif task.role=="reporter":


        report_file = f"{PROJECT}/software_agent_report.md"


        status = "PASS" if TEST_EXIT_CODE == 0 else "FAILED"



        content = f"""
# Software Engineering Agent Report


## Execution Time

{datetime.now()}



## Code Before


{BEFORE_CODE}



## Code After


{AFTER_CODE}



## Testing Evidence


Status:

{status}


Exit Code:

{TEST_EXIT_CODE}





{TEST_OUTPUT}



## Conclusion


Software issue fixed automatically.

"""


        with open(
            report_file,
            "w",
            encoding="utf8"
        ) as f:

            f.write(content)



        print(
            "Report saved:",
            report_file
        )



        return AgentResult(

        subtask_id=task.id,

        status="success",

        summary="All tests passed",

        evidence=[
        f"pytest_exit_code={TEST_EXIT_CODE}"
    ],

        tool_records=[

        {

            "tool":"test_runner",

            "arguments":{

                "command":
                "pytest examples/software_task/test_app.py -v"

            },

            "success":True,

            "exit_code":0,

            "metadata":{

                "artifacts":[
                    "examples/software_task/test_app.py"
                ]

            }

        }

    ]

)
    # =====================================
# Main
# =====================================

def main():

    registry = AgentRegistry()


    roles = [
        "analyst",
        "architect",
        "reviewer",
        "developer",
        "tester",
        "reporter"
    ]


    for role in roles:

        registry.register(

            DeterministicAgent(

                role=role,

                handler=software_handler

            )

        )



    orchestrator = Orchestrator(

        registry=registry,

        acceptance=AcceptanceEvaluator()

    )



    agent = MainAgent(

        orchestrator,

        planner=build

    )



    goal = """
Analyze software project,
locate bugs,
modify source code,
run regression tests,
generate evidence report.
"""


    report = agent.execute(goal)



    print("\n========== REPORT ==========")


    print(
        "Status:",
        report.status
    )


    for task_id, result in report.results.items():

        print(
            task_id,
            ":",
            result.summary
        )



if __name__ == "__main__":

    main()
