from pathlib import Path

from core.models import Plan, SubTask
from core.domains import DomainAdapter

from core.tools.shell_runner import ShellRunner
from core.tools.test_runner import TestRunner
from domains.software_agents import create_software_agents


class SoftwareDomainAdapter(DomainAdapter):

    name = "software"


    # =====================================
    # 注册工具
    # =====================================

    def register_tools(
        self,
        registry,
        workspace
    ):

        shell_runner = ShellRunner(
            workspace
        )


        registry.register(
            shell_runner
        )


        test_runner = TestRunner(
            shell_runner
        )


        registry.register(
            test_runner
        )

        return registry

    # =====================================
    # Agent注册
    # =====================================

    def build_agents(
        self,
        model_client,
        tools
    ):

        # 当前 demo 使用 DeterministicAgent
        # 在 run_software_demo.py 注册
        from domains.software_agents import create_software_agents

        return create_software_agents()



    # =====================================
    # 软件任务DAG
    # =====================================

    def build_plan(
        self,
        goal: str
    ) -> Plan:


        workspace = (
            "examples/software_task"
        )


        tasks = [

            SubTask(

                id="requirements_analysis",

                role="analyst",

                description=
                "读取需求文档，分析业务目标并生成需求分析",

                depends_on=[],


                inputs=[

                    "requirements.md"

                ],


                acceptance=[

                    "requirement_analysis_generated"

                ],


                max_retries=1,


                metadata={

                    "workspace":
                    workspace,


                    "expected_outputs":[

                        "artifacts/requirement_analysis.md"

                    ],


                    "checks":[

                        {

                        "id":
                        "requirement_analysis_exists",

                        "check_type":
                        "file_exists"

                        }

                    ]

                }

            ),



            SubTask(

                id="architecture",

                role="architect",

                description=
                "设计软件模块结构",

                depends_on=[

                    "requirements_analysis"

                ],


                inputs=[

                    "requirements.md"

                ],


                acceptance=[

                    "architecture_generated"

                ],


                max_retries=1,


                metadata={

                    "workspace":
                    workspace,


                    "expected_outputs":[

                        "artifacts/architecture_design.md"

                    ]

                }

            ),



            SubTask(

                id="implementation",

                role="developer",

                description=
                "修改代码实现需求",

                depends_on=[

                    "architecture"

                ],


                inputs=[

                    "src/app.py"

                ],


                acceptance=[

                    "tests_pass"

                ],


                max_retries=2,


                metadata={

                    "workspace":
                    workspace,


                    "expected_outputs":[

                        "src/app.py"

                    ]

                }

            ),



            SubTask(

                id="testing",

                role="tester",

                description=
                "运行自动化测试",

                depends_on=[

                    "implementation"

                ],


                inputs=[

                    "tests/test_app.py"

                ],


                acceptance=[

                    "pytest_pass"

                ],


                max_retries=1,


                metadata={

                    "workspace":
                    workspace,


                    "checks":[

                        {

                        "id":
                        "pytest_pass",

                        "check_type":
                        "command",

                        "command":
                        "pytest tests/test_app.py -v"

                        }

                    ]

                }

            ),



            SubTask(

                id="review",

                role="reviewer",

                description=
                "检查代码质量和实现结果",

                depends_on=[

                    "testing"

                ],


                inputs=[

                    "src/app.py"

                ],


                acceptance=[

                    "review_complete"

                ],


                max_retries=1,


                metadata={

                    "workspace":
                    workspace

                }

            )

        ]



        return Plan(

            goal=goal,


            subtasks=tasks,


            final_acceptance=[


                "src/app.py exists",


                "pytest tests/test_app.py -v passed",


                "review_complete"

            ]

        )



    # =====================================
    # 长程Contract
    # =====================================

    def build_contract(
        self,
        goal
    ):


        from core.long_horizon.acceptance_contract import AcceptanceContract


        return AcceptanceContract(

            name="software_contract",


            criteria=[

                "src/app.py exists",

                "pytest passed",

                "review_complete"

            ]

        )



    # =====================================
    # 重置workspace
    # =====================================

    def reset_workspace(
        self,
        workspace
    ):

        workspace = Path(workspace)


        artifacts = (
            workspace /
            "artifacts"
        )


        artifacts.mkdir(
            exist_ok=True
        )
