import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.long_horizon import StructuredGoalContractGenerator


class UnusedClient:
    pass


def test_contract_generation_prompt_uses_only_current_goal_as_requirement_source():
    generator = StructuredGoalContractGenerator(UnusedClient())
    messages = generator._messages("实现一个加法计算器", plan_hint=None, domain=None)
    payload = messages[1]["content"]

    assert '"original_user_goal": "实现一个加法计算器"' in payload
    assert '"initial_plan_hint": null' in payload
    assert "sole source of requirements" in payload
    assert "Do not expand a narrow task" in payload
