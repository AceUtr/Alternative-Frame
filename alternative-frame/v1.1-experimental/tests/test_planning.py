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


def test_calculator_goal_does_not_inherit_generic_android_assistant_template():
    goal = "制作一个科学计算器，支持三角函数和括号运算"
    plan = PlanningPipeline().build(goal)

    assert plan.goal == goal
    assert {task.id for task in plan.subtasks} == {"implementation", "tests"}
    assert all("认证" not in task.description for task in plan.subtasks)
    assert all("requirements.md" not in task.metadata.get("expected_outputs", []) for task in plan.subtasks)


def test_calculator_plan_requires_a_real_engine_and_successful_powershell_tests():
    plan = PlanningPipeline().build("制作一个科学计算器，支持三角函数和括号运算")
    tasks = {task.id: task for task in plan.subtasks}

    assert tasks["implementation"].metadata["expected_outputs"] == ["src/CalculatorEngine.psm1", "calculator.ps1"]
    assert tasks["tests"].metadata["expected_outputs"] == ["tests/test_calculator.ps1"]
    assert {
        (check["check_type"], check.get("command"))
        for check in tasks["tests"].metadata["checks"]
    } >= {
        ("file_exists", None),
        ("command", "pwsh -NoProfile -File tests/test_calculator.ps1"),
    }
