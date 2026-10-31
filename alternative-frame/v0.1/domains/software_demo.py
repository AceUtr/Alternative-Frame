from core.models import Plan, SubTask



def build(goal: str) -> Plan:


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
                "examples/software_task/requirements.md",
                "examples/software_task/app.py",
                "examples/software_task/test_app.py"
            ],

            acceptance=[
                "生成需求分析结果",
                "明确功能验收条件"
            ],

            metadata={
                "domain":
                "software_engineering"
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

            acceptance=[
                "完成系统结构设计"
            ],

            metadata={
                "domain":
                "software_engineering"
            }

        ),




        # ======================
        # 3. Code Review
        # ======================

        SubTask(
            id="code_review",

            role="reviewer",

            description=
            "检查现有代码，定位缺陷并分析修改方案",

            depends_on=[
                "architecture_design"
            ],

            inputs=[
                "examples/software_task/app.py",
                "examples/software_task/test_app.py"
            ],

            acceptance=[
                "发现代码问题",
                "提供修复建议"
            ],

            metadata={
                "domain":
                "software_engineering"
            }

        ),




        # ======================
        # 4. Developer
        # ======================

        SubTask(
            id="implementation",

            role="developer",

            description=
            "根据代码审查结果修改软件实现",

            depends_on=[
                "code_review"
            ],

            acceptance=[
                "代码修改完成",
                "功能符合需求"
            ],

            metadata={
                "domain":
                "software_engineering"
            }

        ),





        # ======================
        # 5. Tester
        # ======================

        SubTask(
            id="testing",

            role="tester",

            description=
            "执行自动化测试并验证修改结果",

            depends_on=[
                "implementation"
            ],

            acceptance=[
                "所有测试通过"
            ],

            metadata={
                "domain":
                "software_engineering",

                "command":
                "pytest"
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
                "testing"
            ],

            acceptance=[
                "生成完整运行报告",
                "保存测试日志"
            ],

            metadata={
                "domain":
                "software_engineering"
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

            "生成运行证据"

        ]

    )
