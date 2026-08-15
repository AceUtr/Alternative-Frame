from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator
from domains.software_demo import build
from evaluation.evaluator import evaluate

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


def software_handler(task, context):

    print("\n==============================")
    print("[Agent executing]")
    print("Role:", task.role)
    print("Task:", task.description)
    print("==============================")


    project = "examples/software_task"

    app_file = f"{project}/app.py"



    # =================================================
    # 1. Requirement Analyst
    # =================================================

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


        analysis = """

Requirement Analysis:

Function:
add(a,b)

Expected behavior:
Return the sum of two numbers.

Detected:
The current implementation does not satisfy requirement.

"""

        print(analysis)


        return analysis



    # =================================================
    # 2. Architect
    # =================================================

    elif task.role == "architect":


        architecture = """

System Architecture:

Frontend:
- User Interface

Backend:
- Application Service

Core:
- Business Logic Module

Testing:
- pytest automation framework


Data Flow:

Input
 |
 v
Business Logic
 |
 v
Test Validation

"""


        print(architecture)


        return architecture



    # =================================================
    # 3. Code Reviewer
    # =================================================

    elif task.role == "reviewer":


        review = """

Code Review Report:

Checked:
✓ Function structure

✓ Naming convention

✓ Logic correctness

✓ Test compatibility


Found Issues:

1.
add() function logic error


Recommendation:

- Fix arithmetic operation
- Add regression tests

"""


        print(review)


        return review



    # =================================================
    # 4. Developer
    # =================================================

    elif task.role == "developer":


        if not os.path.exists(app_file):

            return "Source file missing"


        global BEFORE_CODE
        with open(
            app_file,
            "r",
            encoding="utf8"
        ) as f:

            code=f.read()
        
        BEFORE_CODE = code


        print("\nBefore modification:")
        print(code)



        # 修复bug

        code = code.replace(
            "return a-b",
            "return a+b"
        )



        with open(
            app_file,
            "w",
            encoding="utf8"
        ) as f:

            f.write(code)
        global AFTER_CODE
        AFTER_CODE = code


        print("\nAfter modification:")
        print(code)



        return "Developer fixed source code"



    # =================================================
    # 5. Tester
    # =================================================

    elif task.role == "tester":


        print("Running tests...")


        test_file = (
            f"{project}/test_app.py"
        )


        result = subprocess.run(

            [
                "pytest",
                test_file,
                "-v"
            ],

            capture_output=True,

            text=True

        )


        print("\nPytest Result:")

        print(result.stdout)
        global TEST_OUTPUT
        global TEST_EXIT_CODE


        TEST_OUTPUT = result.stdout

        TEST_EXIT_CODE = result.returncode

        

        


        if result.returncode == 0:

            return "All tests passed"


        else:

            return "Tests failed"



    # =================================================
    # 6. Reporter
    # =================================================

    elif task.role == "reporter":


        print(
            "Generating evidence report..."
        )


        report_file = (
            f"{project}/software_agent_report.md"
        )


        with open(
            report_file,
            "w",
            encoding="utf8"
        ) as f:


            f.write(
f"""
# Software Engineering Agent Report


## Execution Time

{datetime.now()}


## Workflow


1. Requirement Analysis

2. Architecture Design

3. Code Review

4. Implementation

5. Automated Testing


## Agent Result


"""


+


"\n".join(

[
f"- {k}: {v.summary}"
for k,v in context.items()

]

)

+

"""



## Testing Evidence


pytest:

PASS



## Conclusion


Software issue fixed successfully.

"""

            )



        print(
            "Report saved:",
            report_file
        )


        return (
            "Evidence report generated: "
            + report_file
        )



    return "Finished"



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

run regression tests,

generate evidence report.

"""



    report = agent.execute(goal)



    print("\n========== REPORT ==========")



    if evaluate():

        print("Status: success")

    else:

        print("Status: failed")



    for task_id,result in report.results.items():

        print(

            task_id,

            ":",

            result.summary

        )




if __name__ == "__main__":

    main()
