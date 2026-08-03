from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator
from domains.software_demo import build
from evaluator.evaluator import evaluate
from core.acceptance import AcceptanceEvaluator

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

    global BEFORE_CODE
    global AFTER_CODE
    global TEST_OUTPUT
    global TEST_EXIT_CODE


    print("\n==============================")
    print("[Agent executing]")
    print("Role:", task.role)
    print("Task:", task.description)
    print("==============================")


    project = "examples/software_task"

    app_file = f"{project}/app.py"



    # =================================================
    # 1. Analyst
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
    # 3. Reviewer
    # =================================================

    elif task.role == "reviewer":


    with open(
        app_file,
        "r",
        encoding="utf8"
    ) as f:

        code = f.read()



    requirement_result = context.get(
        "requirements_analysis"
    )


    requirement_text = ""


    if requirement_result:

        requirement_text = requirement_result.summary



    print("\nReviewer received context:")

    print(requirement_text)



    if (
        "return b-a" in code
        or
        "return a-b" in code
    ):


        review = """

Code Review Report:


Issue:

Function add() contains incorrect arithmetic logic.


Current implementation:

{}

Expected:

return a+b


Recommendation:

Replace subtraction with addition.

""".format(code)


    else:


        review = """

Code Review Report:

No obvious issue found.

"""



    print(review)


    return review


    # =================================================
    # 4. Developer
    # =================================================

    elif task.role == "developer":


        if not os.path.exists(app_file):

            return "Source file missing"



        with open(
            app_file,
            "r",
            encoding="utf8"
        ) as f:

            code = f.read()



        BEFORE_CODE = code



        print("\nBefore modification:")
        print(code)



        # apply fix

        review_result = context.get(
    "code_review"
)


if review_result:

    print("\nDeveloper received review:")

    print(
        review_result.summary
    )



code = code.replace(
    "return a-b",
    "return a+b"
)


code = code.replace(
    "return b-a",
    "return a+b"
)



        with open(
            app_file,
            "w",
            encoding="utf8"
        ) as f:

            f.write(code)



        AFTER_CODE = code



        print("\nAfter modification:")
        print(code)



        return AgentResult(

    subtask_id=task.id,

    status="success",

    summary="Developer fixed source code",

    artifacts=[
        "examples/software_task/app.py"
    ]

)



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



        TEST_OUTPUT = result.stdout

        TEST_EXIT_CODE = result.returncode



        print("\nPytest Result:")

        print(TEST_OUTPUT)



        if result.returncode == 0:

            from core.models import AgentResult
            return AgentResult(

    subtask_id=task.id,

    status="success",

    summary="All tests passed",

    evidence=[
        f"pytest_exit_code={TEST_EXIT_CODE}"
    ]

    )

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



        if TEST_EXIT_CODE == 0:

            test_status = "PASS"

        else:

            test_status = "FAILED"



        report_content = f"""
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



        report_content += "\n".join(

            [
                f"- {k}: {v.summary}"
                for k, v in context.items()
            ]

        )



        report_content += f"""


## Code Change



### Before


{BEFORE_CODE}



### After


{AFTER_CODE}



## Testing Evidence



pytest Status:


{test_status}



Output:


{TEST_OUTPUT}



## Conclusion


Software issue fixed successfully.

"""



        with open(
            report_file,
            "w",
            encoding="utf8"
        ) as f:

            f.write(report_content)



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



    from core.acceptance import AcceptanceEvaluator


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



    if evaluate():

        print("Status: success")

    else:

        print("Status: failed")



    for task_id, result in report.results.items():

        print(

            task_id,

            ":",

            result.summary

        )





if __name__ == "__main__":

    main()
