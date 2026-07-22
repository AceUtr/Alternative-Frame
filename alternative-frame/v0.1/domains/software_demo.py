from core.models import Plan, SubTask


def build(goal:str):

    return Plan(
        goal=goal,

        subtasks=[

            SubTask(
                id="analyze",
                role="analyst",
                description="分析Python项目代码",
                acceptance=[
                    "找到bug原因"
                ]
            ),


            SubTask(
                id="fix",
                role="developer",
                description="修改代码",
                depends_on=[
                    "analyze"
                ],
                acceptance=[
                    "代码修改完成"
                ]
            ),


            SubTask(
                id="test",
                role="tester",
                description="运行pytest测试",
                depends_on=[
                    "fix"
                ],
                acceptance=[
                    "测试通过"
                ]
            )
        ]
    )
