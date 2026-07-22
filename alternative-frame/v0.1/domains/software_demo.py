from core.models import Plan, SubTask


def build(goal: str) -> Plan:

    tasks = [

        SubTask(
            id="analyze_project",
            role="analyst",
            description="读取软件项目文件并分析问题",
            inputs=[
                "examples/software_task"
            ],
            acceptance=[
                "完成代码问题分析"
            ]
        ),


        SubTask(
            id="modify_code",
            role="developer",
            description="根据分析结果修改代码",
            depends_on=[
                "analyze_project"
            ],
            acceptance=[
                "代码修改完成"
            ]
        ),


        SubTask(
            id="run_test",
            role="tester",
            description="运行自动化测试验证修改结果",
            depends_on=[
                "modify_code"
            ],
            acceptance=[
                "测试全部通过"
            ]
        )
    ]


    return Plan(
        goal=goal,
        subtasks=tasks,
        final_acceptance=[
            "软件问题修复完成",
            "测试通过"
        ]
    )
