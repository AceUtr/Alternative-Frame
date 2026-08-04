from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator
from domains.software_demo import SoftwareDomainAdapter


from core.acceptance import AcceptanceEvaluator
from core.models import AgentResult


import os
import subprocess
import difflib
from pathlib import Path
from datetime import datetime



# ==========================
# Evidence Storage
# ==========================

BEFORE_CODE = ""
AFTER_CODE = ""

TEST_OUTPUT = ""
TEST_EXIT_CODE = None



from pathlib import Path


ROOT_DIR = Path(__file__).parent


PROJECT = ROOT_DIR / "examples" / "software_task"

APP_FILE = PROJECT / "app.py"

TEST_FILE = PROJECT / "test_app.py"



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

            code = f.read()



        BEFORE_CODE = code


        print("\nBefore:")
        print(code)



        # ==========================
        # Retry Information
        # ==========================

        attempt = task.metadata.get(
            "runtime_attempt",
            1
        )


        retry_feedback = task.metadata.get(
            "retry_feedback"
        )


        print(
            "\nDeveloper attempt:",
            attempt
        )


        if retry_feedback:

            print(
                "\nRetry feedback:"
            )

            print(
                retry_feedback
            )



        # ==========================
        # First attempt:
        # simulate imperfect fix
        # ==========================

        if attempt == 1:


            code = code.replace(
                "return a-b",
                "return a*b"
            )


            code = code.replace(
                "return b-a",
                "return a*b"
            )


            print(
                "\nFirst attempt generated a wrong implementation."
            )



        # ==========================
        # Retry attempt
        # ==========================

        else:


            code = code.replace(
                "return a-b",
                "return a+b"
            )


            code = code.replace(
                "return b-a",
                "return a+b"
            )


            code = code.replace(
                "return a*b",
                "return a+b"
            )


            print(
                "\nRetry attempt fixed implementation."
            )



        with open(
            APP_FILE,
            "w",
            encoding="utf8"
        ) as f:

            f.write(code)



        AFTER_CODE = code



        print("\nAfter:")
        print(code)



        # ==========================
        # Run verification test
        # Through ToolRegistry
        # ==========================

        print(
            "\nDeveloper running verification test..."
        )

        command = (
            f"pytest {TEST_FILE} -v"
        )


        tool_result = context["tools"].execute(

            
            "test_runner",
            {
                "command": command
            }
                

        )



        test_output = tool_result.output


        test_exit_code = tool_result.exit_code



        print(test_output)



        test_success = (

            test_exit_code == 0

        )



        # ==========================
        # Return real evidence
        # ==========================

        if test_success:


            return AgentResult(

                subtask_id=task.id,

                status="success",

                summary=
                "Source code modified and verified",


                artifacts=[

                    APP_FILE

                ],


                evidence=[

                    "developer_completed",

                    "implementation_test_passed"

                ],


                tool_records=[

                    {

                        "tool":
                        "test_runner",


                        "arguments":

                        {

                            "command":
                            f"pytest {TEST_FILE} -v"
                        },


                        "success":
                        True,


                        "exit_code":
                        test_exit_code,


                        "metadata":

                        {

                            "artifacts":

                            [

                                APP_FILE

                            ]

                        }

                    }

                ]

            )



        else:


            return AgentResult(

                subtask_id=task.id,


                status="failed",


                summary=
                "Source code modified but verification failed",


                artifacts=[

                    APP_FILE

                ],


                evidence=[

                    "developer_completed",

                    "implementation_test_failed"

                ],


                failures=[

                    test_output

                ],


                tool_records=[

                    {

                        "tool":
                        "test_runner",


                        "arguments":

                        {

                            "command":
                            f"pytest {TEST_FILE} -v"

                        },


                        "success":
                        False,


                        "exit_code":
                        test_exit_code,


                        "metadata":

                        {

                            "artifacts":

                            [

                                APP_FILE

                            ]

                        }

                    }

                ]

            )

    # =====================================
    # Tester
    # =====================================


    elif task.role == "tester":

        print("Running tests...")


        command = (
            f"pytest {TEST_FILE} -v"
        )


        # =====================================
        # 使用工具执行测试
        # =====================================

        tool_result = context["tools"].execute(
            "test_runner",
            
            {
                "command": command
            }
            
        )


        TEST_OUTPUT = tool_result.output

        TEST_EXIT_CODE = tool_result.exit_code



        print(TEST_OUTPUT)



        test_success = (
            TEST_EXIT_CODE == 0
        )



        # =====================================
        # 测试通过
        # =====================================

        if test_success:


            return AgentResult(

                subtask_id=task.id,

                status="success",


                summary=
                "Regression tests passed",


                artifacts=[

                    "examples/software_task/test_app.py"

                ],


                evidence=[

                    f"command={command}",

                    f"exit_code={TEST_EXIT_CODE}",

                    "real_test_execution"

                ],


                tool_records=[

                    {

                        "tool":
                        "test_runner",


                        "arguments":{

                            "command":
                            command

                        },


                        "success":
                        True,


                        "exit_code":
                        TEST_EXIT_CODE,


                        "output_summary":
                        TEST_OUTPUT[-1000:],


                        "metadata":{

                            "artifacts":[

                                "examples/software_task/test_app.py"

                            ]

                        }

                    }

                ]

            )



        # =====================================
        # 测试失败
        # =====================================

        else:


            return AgentResult(

                subtask_id=task.id,


                status="failed",


                summary=
                "Regression tests failed",


                artifacts=[

                    "examples/software_task/test_app.py"

                ],


                failures=[

                    TEST_OUTPUT

                ],


                evidence=[

                    f"command={command}",

                    f"exit_code={TEST_EXIT_CODE}",

                    "real_test_execution_failed"

                ],


                tool_records=[

                    {

                        "tool":
                        "test_runner",


                        "arguments":{

                            "command":
                            command

                        },


                        "success":
                        False,


                        "exit_code":
                        TEST_EXIT_CODE,


                        "output_summary":
                        TEST_OUTPUT[-1000:],


                        "metadata":{

                            "artifacts":[

                                "examples/software_task/test_app.py"

                            ]

                        }

                    }

                ]

            )

    # =====================================
    # Reporter
    # =====================================


    elif task.role == "reporter":

        from pathlib import Path
        import difflib


        workspace = Path(PROJECT)


        artifact_dir = (
            workspace /
            "artifacts"
        )


        artifact_dir.mkdir(
            exist_ok=True
        )


        report_file = (
            artifact_dir /
            "software_report.md"
        )


        # ==========================
        # Test evidence
        # ==========================

        test_success = (
            TEST_EXIT_CODE == 0
        )


        status = (
            "PASS"
            if test_success
            else "FAILED"
        )



        # ==========================
        # Code diff
        # ==========================

        diff = "\n".join(

            difflib.unified_diff(

                BEFORE_CODE.splitlines(),

                AFTER_CODE.splitlines(),

                fromfile="before/app.py",

                tofile="after/app.py",

                lineterm=""

            )

        )



        # ==========================
        # Generate report
        # ==========================

        content = f"""
# Software Engineering Agent Report


## Execution Evidence


Status:

{status}



## Modified File


examples/software_task/app.py



## Code Before


{BEFORE_CODE}



## Code After


{AFTER_CODE}



## Change Diff


{diff}



## Test Command


pytest examples/software_task/test_app.py -v



## Test Exit Code


{TEST_EXIT_CODE}



## Test Output


{TEST_OUTPUT}



## Risk


No additional risk detected.

"""


        report_file.write_text(

            content,

            encoding="utf8"

        )


        print(

            "Report saved:",

            report_file

        )



        return AgentResult(

            subtask_id=task.id,


            status=(

                "success"

                if test_success

                else "failed"

            ),


            summary=(

                "Evidence report generated"

                if test_success

                else "Evidence report generated but tests failed"

            ),


            artifacts=[

                str(report_file)

            ],


            evidence=[

                f"pytest_exit_code={TEST_EXIT_CODE}",

                "runtime_report_generated"

            ],


            failures=(

                []

                if test_success

                else [

                    "pytest failed"

                ]

            ),


            tool_records=[

                {

                    "tool":

                    "test_runner",


                    "arguments":

                    {

                        "command":

                        "pytest examples/software_task/test_app.py -v"

                    },


                    "success":

                    test_success,


                    "exit_code":

                    TEST_EXIT_CODE,


                    "output_summary":

                    TEST_OUTPUT[-1000:]

                }

            ]

        )
    # =====================================
# Main
# =====================================

# =====================================
# Main
# =====================================

def main():


    workspace = "examples/software_task"


    # ==========================
    # 1. 创建领域Adapter
    # ==========================

    adapter = SoftwareDomainAdapter()



    # ==========================
    # 2. 配置领域
    # ==========================

    tools, agent_registry = adapter.configure(
        workspace=workspace
    )



    # ==========================
    # 3. 注册Agent
    # ==========================

    roles = [

        "analyst",
        "architect",
        "reviewer",
        "developer",
        "tester",
        "reporter"

    ]


    for role in roles:

        agent_registry.register(

            DeterministicAgent(

                role=role,

                handler=software_handler

            )

        )



    # ==========================
    # 4. Orchestrator
    # ==========================

    orchestrator = Orchestrator(

        registry=agent_registry,

        acceptance=AcceptanceEvaluator(),

        tools=tools
    )



    # ==========================
    # 5. Main Agent
    # ==========================

    agent = MainAgent(

        orchestrator,

        planner=adapter.build_plan

    )



    # ==========================
    # 6. Goal
    # ==========================

    goal = """

Analyze software project,

locate bugs,

modify source code,

run regression tests,

generate evidence report.

"""



    # ==========================
    # 7. Build Plan
    # ==========================

    plan = adapter.build_plan(goal)



    # ==========================
    # 8. Execute Agent
    # ==========================

    report = agent.execute(plan)



    # ==========================
    # 9. Output
    # ==========================

   

    print("\n========== REPORT ==========")

    print(
    "Status:",
    report.status
)


    print("\nTasks:")


    for task_id, result in report.results.items():

        print("\n================")
        print("Task:", task_id)

        print(
        "Status:",
        result.status
    )

    print(
        "Summary:",
        result.summary
    )

    print(
        "Failures:"
    )

    for failure in result.failures:
        print(
            " -",
            failure
        )


    print(
        "Evidence:"
    )

    for evidence in result.evidence:
        print(
            " -",
            evidence
        )


    print(
        "Artifacts:"
    )

    for artifact in result.artifacts:
        print(
            " -",
            artifact
        )

if __name__ == "__main__":

    main()
