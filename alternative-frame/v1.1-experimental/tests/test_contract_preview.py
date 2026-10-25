import json

import pytest

from core.long_horizon import AcceptanceContract
from ui import validate_contract_json


GOAL = "实现并测试计算器"


def contract_payload():
    return {
        "goal": GOAL,
        "goal_summary": "实现一个经过测试的计算器",
        "criteria": [
            {
                "id": "source_exists",
                "description": "计算器源码存在",
                "check_type": "file_exists",
                "required": True,
                "path": "calculator.py",
                "command": None,
                "metric_name": None,
                "threshold": None,
            },
            {
                "id": "tests_pass",
                "description": "自动化测试通过",
                "check_type": "command",
                "required": True,
                "path": None,
                "command": "python -m pytest -q",
                "metric_name": None,
                "threshold": None,
            },
        ],
        "constraints": ["不得修改原始目标"],
    }


def validate(payload):
    return validate_contract_json(json.dumps(payload, ensure_ascii=False), GOAL)


def test_valid_edited_contract_is_accepted():
    payload = contract_payload()
    payload["goal_summary"] = "实现计算器并用自动化测试验证"

    contract = validate(payload)

    assert isinstance(contract, AcceptanceContract)
    assert contract.goal_summary == payload["goal_summary"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data.update(goal="替换后的目标"), "original user goal"),
        (lambda data: data["criteria"][0].update(path="C:\\secrets.txt"), "unsafe"),
        (lambda data: data["criteria"][1].update(command="python -m pytest; del /s *"), "forbidden"),
        (lambda data: data["criteria"][0].update(required="true"), "boolean"),
    ],
)
def test_unsafe_edits_are_rejected(mutate, message):
    payload = contract_payload()
    mutate(payload)

    with pytest.raises(ValueError, match=message):
        validate(payload)
