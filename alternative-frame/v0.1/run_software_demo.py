from pathlib import Path

from core.models import AgentResult
from core.agents import (
    DeterministicAgent,
    AgentRegistry
)


ROOT_DIR = Path(__file__).resolve().parent.parent


PROJECT = (
    ROOT_DIR /
    "examples" /
    "software_task"
)


APP_FILE = (
    PROJECT /
    "src" /
    "app.py"
)


TEST_FILE = (
    PROJECT /
    "tests" /
    "test_app.py"
)

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



    # =================================================
    # Analyst
    # =================================================

    if task.role == "analyst":

        with open(
            APP_FILE,
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


            Detected problem:

            Current implementation violates requirement.
        """


        print(analysis)



        analysis_file = (
            PROJECT /
            "artifacts" /
            "requirement_analysis.md"
        )


        analysis_file.parent.mkdir(
            exist_ok=True
        )


        analysis_file.write_text(

            analysis,

            encoding="utf8"

        )


        artifact_dir = PROJECT / "artifacts"

        artifact_dir.mkdir(
            exist_ok=True
        )


        requirement_file = (
            artifact_dir /
            "requirement_analysis.md"
        )


        requirement_file.write_text(
        analysis,
        encoding="utf8"
)



        return AgentResult(

            subtask_id=task.id,

            status="success",

            summary=analysis,

            artifacts=[

                str(requirement_file)

            ],

            evidence=[

                {

                "type":
                "artifact",

                "path":
                str(requirement_file),

                "exists":
                True
                },

                "requirement_analysis_generated"

            ]
        )


    # =================================================
    # Architect
    # =================================================

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



    # =====================================
    # Generate architecture artifact
    # =====================================


        artifact_dir = (

        PROJECT /
        "artifacts"

    )


        artifact_dir.mkdir(

            exist_ok=True

        )



        architecture_file = (

        artifact_dir /
        "architecture_design.md"

    )



        architecture_file.write_text(

        architecture,

        encoding="utf8"

    )



        return AgentResult(


        subtask_id=task.id,


        status="success",


        summary=architecture,


        artifacts=[

            str(architecture_file)

        ],


        evidence=[

            {"type":
            "artifact",

            "path":
            str(architecture_file),

            "exists":
            True
        },

        "architecture_design_generated"
                
        ],


        tool_records=[]

    )

    # =================================================
    # Reviewer
    # =================================================

    elif task.role == "reviewer":


        with open(
            APP_FILE,
            "r",
            encoding="utf8"
        ) as f:

            code = f.read()



        if (
            "return a-b" in code
            or
            "return b-a" in code
        ):


            review = """
Code Review Result:


Bug:

Function add() uses subtraction.


Expected:

return a+b


Solution:

Replace subtraction operator.
"""


        else:


            review = """
Code Review Result:


No bug detected.
"""



        print(review)



        return AgentResult(

            subtask_id=task.id,

            status="success",

            summary=review

        )



    # =================================================
    # Developer
    # =================================================

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



        # =============================================
        # First attempt
        # simulate imperfect implementation
        # =============================================

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
                "\nFirst attempt generated wrong implementation."
            )



        # =============================================
        # Retry attempt
        # =============================================

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
                "\nRetry fixed implementation."
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



        # =============================================
        # Developer verification
        # =============================================

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



        print("\nTEST RESULT:")

        print(test_output)



        test_success = (
            test_exit_code == 0
        )


        # 保存测试证据

        TEST_OUTPUT = test_output

        TEST_EXIT_CODE = test_exit_code



        if test_success:


            return AgentResult(

                subtask_id=task.id,

                status="success",

                summary="Source code modified and verified",


                artifacts=[

                    str(APP_FILE)

                ],


                evidence=[

                    "developer_completed",

                    "tool=test_runner;success=True",

                    "implementation_test_passed"

                ],


                tool_records=[

                    {

                        "tool":
                        "test_runner",


                        "arguments":

                        {

                            "command": command

                        },


                        "success": True,


                        "exit_code":
                        test_exit_code,


                        "metadata":

                        {

                            "artifacts":

                            [

                                str(APP_FILE)

                            ]

                        }

                    }

                ]

            )



        else:


            return AgentResult(

                subtask_id=task.id,


                status="failed",


                summary="Source code modified but verification failed",


                artifacts=[

                    str(APP_FILE)

                ],


                failures=[

                    test_output

                ],


                evidence=[

                    "developer_completed",

                    "tool=test_runner;success=False",

                    "implementation_test_failed"

                ],


                tool_records=[

                    {

                        "tool":
                        "test_runner",


                        "arguments":

                        {

                            "command": command

                        },


                        "success": False,


                        "exit_code":
                        test_exit_code,


                        "metadata":

                        {

                            "artifacts":

                            [

                                str(APP_FILE)

                            ]

                        }

                    }

                ]

            )

        # =================================================
    # Tester
    # =================================================

    elif task.role == "tester":


        print("Running tests...")


        command = (
            f"pytest {TEST_FILE} -v"
        )



        # =============================================
        # 使用 TestRunner 执行真实测试
        # =============================================

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



        if test_success:


            return AgentResult(

                subtask_id=task.id,

                status="success",

                summary="Regression tests passed",


                artifacts=[

                    str(TEST_FILE)

                ],


                evidence=[

                    {

                        "type":
                        "command_execution",


                        "command":
                        command,


                        "exit_code":
                        TEST_EXIT_CODE,


                        "passed":
                        True

                    },


                    {

                        "type":
                        "test_result",


                        "framework":
                        "pytest",


                        "tests_passed":
                        True

                    }

                ],


                tool_records=[

                    {

                        "tool":
                        "test_runner",


                        "arguments":

                        {

                            "command":
                            command

                        },


                        "success":
                        True,


                        "exit_code":
                        TEST_EXIT_CODE,


                        "output_summary":
                        TEST_OUTPUT[-1000:]

                    }

                ]

            )



        else:


            return AgentResult(

                subtask_id=task.id,


                status="failed",


                summary="Regression tests failed",


                artifacts=[

                    str(TEST_FILE)

                ],


                failures=[

                    TEST_OUTPUT

                ],


                evidence=[

                    {

                        "type":
                        "command_execution",


                        "command":
                        command,


                        "exit_code":
                        TEST_EXIT_CODE,


                        "passed":
                        False

                    },


                    {

                        "type":
                        "test_result",


                        "framework":
                        "pytest",


                        "tests_passed":
                        False,


                        "failure_log":
                        TEST_OUTPUT[-2000:]

                    }

                ],


                tool_records=[

                    {

                        "tool":
                        "test_runner",


                        "arguments":

                        {

                            "command":
                            command

                        },


                        "success":
                        False,


                        "exit_code":
                        TEST_EXIT_CODE,


                        "output_summary":
                        TEST_OUTPUT[-1000:]

                    }

                ]

            )



    # =================================================
    # Reporter
    # =================================================

    elif task.role == "reporter":

        import difflib


        artifact_dir = (
            PROJECT /
            "artifacts"
        )


        artifact_dir.mkdir(
            exist_ok=True
        )



        report_file = (
            artifact_dir /
            "software_report.md"
        )


        diff_file = (
            artifact_dir /
            "code_diff.patch"
        )


        test_log_file = (
            artifact_dir /
            "test_log.txt"
        )



        test_success = (
            TEST_EXIT_CODE == 0
        )


        status = (
            "PASS"
            if test_success
            else "FAILED"
        )



    # ==========================
    # Generate code diff
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


        diff_file.write_text(

            diff,

            encoding="utf8"

        )



    # ==========================
    # Save test log
    # ==========================

        test_log_file.write_text(

            TEST_OUTPUT,

            encoding="utf8"

        )



    # ==========================
    # Generate markdown report
    # ==========================

    content = f"""
# Software Engineering Agent Report


## Execution Evidence

Status:

{status}



## Modified File

examples/software_task/src/app.py



## Code Before

```python
{BEFORE_CODE}
"""

def build_software_agents():

    registry = AgentRegistry()


    roles=[
        "analyst",
        "architect",
        "developer",
        "tester",
        "reviewer",
        "reporter"
    ]


    for role in roles:

        registry.register(

            DeterministicAgent(
                role=role,
                handler=software_handler
            )

        )

    return registry
