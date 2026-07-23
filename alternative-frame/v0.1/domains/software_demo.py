from core.models import Plan, SubTask


def build(goal: str) -> Plan:

    tasks = [

        SubTask(
            id="analyze_project",
            role="analyst",
            description="读取软件项目文件，分析代码结构并定位问题",
            inputs=[
                "examples/software_task"
            ],
            acceptance=[
                "完成代码问题分析"
            ],
            metadata={
                "domain": "software_engineering"
            }
        ),


        SubTask(
            id="modify_code",
            role="developer",
            description="根据分析结果修改项目代码",
            depends_on=[
                "analyze_project"
            ],
            acceptance=[
                "代码修改完成"
            ],
            metadata={
                "domain": "software_engineering"
            }
        ),


        SubTask(
            id="run_test",
            role="tester",
            description="运行自动化测试验证代码修改结果",
            depends_on=[
                "modify_code"
            ],
            acceptance=[
                "测试全部通过"
            ],
            metadata={
                "domain": "software_engineering",
                "command": "pytest"
            }
        )
    ]


    return Plan(
        goal=goal,
        subtasks=tasks,
        final_acceptance=[
            "代码问题解决",
            "自动化测试通过"
        ]
    )
