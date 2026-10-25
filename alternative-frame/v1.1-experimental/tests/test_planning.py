import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.planning import PlanningPipeline


def test_software_goal_builds_dag():
    plan = PlanningPipeline().build("开发一个 FastAPI 服务，需要测试、部署和 API 文档")
    assert plan.subtasks[0].role == "analyst"
    assert {task.id for task in plan.subtasks} >= {"implementation_auth", "implementation_service"}
    assert all(task.acceptance for task in plan.subtasks)


def test_research_goal_builds_dag():
    plan = PlanningPipeline().build("研究一个训练优化方案并运行实验")
    assert {task.role for task in plan.subtasks} >= {"researcher", "experimenter", "reviewer"}
