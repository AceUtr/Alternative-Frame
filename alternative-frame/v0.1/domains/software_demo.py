from core.models import Plan, SubTask
from core.domains import DomainAdapter

from core.tools.file_editor import FileEditor
from core.tools.shell_runner import ShellRunner
from core.tools.test_runner import TestRunner

def build(goal: str) -> Plan:


    workspace = "examples/software_task"


    tasks = [


        # ======================
        # 1. Requirement Analyst
        # ======================

        SubTask(
            id="requirements_analysis",

            role="analyst",

            description=
            "读取需求文档，分析业务目标并生成验收条件",

            inputs=[
                f"{workspace}/requirements.md",
                f"{workspace}/app.py",
                f"{workspace}/test_app.py"
            ],

            acceptance=[
                "生成需求分析结果",
                "明确功能验收条件"
            ],

            max_retries=2,

            metadata={

                "domain":
                "software_engineering",

                "workspace":
                workspace

            }
        ),



        # ======================
        # 2. Architecture Design
        # ======================

        SubTask(
            id="architecture_design",

            role="architect",

            description=
            "设计软件模块结构、接口和数据模型",

            depends_on=[
                "requirements_analysis"
            ],

            inputs=[
                f"{workspace}/requirements.md"
            ],

            acceptance=[
                "完成系统结构设计"
            ],

            max_retries=2,

            metadata={

                "domain":
                "software_engineering",

                "workspace":
                workspace

            }

        ),



        # ======================
        # 3. Developer Implementation
        # ======================

                SubTask(

            id="implementation",

            role="developer",

            description=
            "根据需求分析和架构设计修改软件实现",


            depends_on=[

                "architecture_design"

            ],


            inputs=[

                f"{workspace}/app.py",
                f"{workspace}/test_app.py"

            ],


            acceptance=[

                "代码修改完成",

                "功能符合需求",

                "自动化测试通过"

            ],


            max_retries=2,


            metadata={


                "domain":

                "software_engineering",


                "workspace":

                workspace,


                # Developer生成的真实产物

                "expected_outputs":[

                    "app.py"

                ],



                # 增加机器验收条件
                # 让developer第一次错误修改时触发retry

                "checks":[


                    {

                        "id":

                        "implementation_tests_pass",


                        "check_type":

                        "command",


                        "command":

                        "pytest test_app.py -v"

                    }


                ]

            }

        ),

        # ======================
        # 4. Tester
        # ======================

        SubTask(
            id="testing",

            role="tester",

            description=
            "执行自动化测试并验证修改结果",

            depends_on=[
                "implementation"
            ],

            max_retries=0,
            inputs=[
                f"{workspace}/test_app.py",
                f"{workspace}/app.py"
            ],

            acceptance=[
                "所有测试通过"
            ],

            

            metadata={

                "domain":
                "software_engineering",

                "workspace":
                workspace,

                "command":
                "pytest",

                "checks":[

                    {
                        "id":
                        "tests_pass",

                        "check_type":
                        "command",

                        "command":
                        "pytest test_app.py -v"

                    }

                ]

            }

        ),



        # ======================
        # 5. Final Code Review
        # ======================

        SubTask(
            id="code_review",

            role="reviewer",

            description=
            "检查修改后的代码和测试结果，完成最终质量审查",

            depends_on=[
                "testing"
            ],

            max_retries=0,

            inputs=[
                f"{workspace}/app.py",
                f"{workspace}/test_app.py"
            ],

            acceptance=[

                "确认代码满足需求",

                "确认测试结果通过"

            ],



            metadata={

                "domain":
                "software_engineering",

                "workspace":
                workspace

            }

        ),



        # ======================
        # 6. Evidence Reporter
        # ======================

        SubTask(
            id="evidence_collection",

            role="reporter",

            description=
            "收集代码修改记录、测试结果和运行证据",

            depends_on=[
                "code_review"
            ],

            max_retries=0,
            acceptance=[

                "生成完整运行报告",

                "保存测试日志"

            ],

            

            metadata={

                "domain":
                "software_engineering",

                "workspace":
                workspace

            }

        )

    ]



    return Plan(

        goal=goal,

        subtasks=tasks,


        final_acceptance=[

            "需求分析完成",

            "代码问题修复",

            "自动化测试通过",

            "代码最终审查完成",

            "生成运行证据"

        ]

    )



class SoftwareDomainAdapter(DomainAdapter):

    name = "software"


    def register_tools(
        self,
        registry,
        workspace
    ):

        shell_runner = ShellRunner(
            workspace
        )


        registry.register(
            FileEditor(workspace)
        )


        registry.register(
            shell_runner
        )


        registry.register(
            TestRunner(shell_runner)
        )



    def build_agents(
        self,
        model_client,
        tools
    ):

        # 后续接入 analyst/developer/tester
        return []



    def build_plan(
        self,
        goal: str
    ) -> Plan:

        return build(goal)



    def build_contract(
        self,
        goal: str
    ):

        from core.long_horizon.acceptance_contract import AcceptanceContract


        return AcceptanceContract(

            name="software_contract",

            criteria=[

                "app.py exists",

                "pytest passed"

            ]

        )



    def reset_workspace(
        self,
        workspace
    ):

        pass
