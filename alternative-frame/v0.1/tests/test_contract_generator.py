import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.long_horizon import (
    AcceptanceContract,
    ContractValidationError,
    ContractValidator,
    GoalCriterion,
    StructuredContractError,
    StructuredGoalContractGenerator,
)
from core.models import Plan, SubTask


def valid_contract_payload():
    return {
        "goal_summary": "Implement a tested service with documentation and secure password storage.",
        "criteria": [
            {
                "id": "source_exists",
                "description": "The authentication implementation exists.",
                "check_type": "file_exists",
                "required": True,
                "path": "src/auth.py",
                "command": None,
                "metric_name": None,
                "threshold": None,
            },
            {
                "id": "tests_pass",
                "description": "Authentication tests pass.",
                "check_type": "command",
                "required": True,
                "path": None,
                "command": "python -m unittest -v tests.test_auth",
                "metric_name": None,
                "threshold": None,
            },
            {
                "id": "password_secure",
                "description": "Passwords are never stored as plaintext.",
                "check_type": "semantic",
                "required": True,
                "path": None,
                "command": None,
                "metric_name": None,
                "threshold": None,
            },
        ],
        "constraints": ["Only modify files inside the workspace."],
    }


class SequenceClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0
        self.messages = []

    def chat(self, messages, tools=None):
        self.calls += 1
        self.messages.append(messages)
        payload = self.payloads.pop(0)
        return {"content": payload if isinstance(payload, str) else json.dumps(payload)}


def test_generator_returns_a_valid_atomic_contract():
    events = []
    client = SequenceClient([valid_contract_payload()])
    generator = StructuredGoalContractGenerator(
        client,
        on_event=lambda event, payload: events.append(event),
    )
    goal = "Implement auth, tests, docs, and secure password storage"
    hint = Plan("initial", [SubTask("auth", "developer", "implement auth")])

    contract = generator.generate(goal, hint, domain="software_engineering")

    assert contract.goal == goal
    assert contract.goal_summary.startswith("Implement a tested service")
    assert [criterion.id for criterion in contract.criteria] == [
        "source_exists",
        "tests_pass",
        "password_secure",
    ]
    assert contract.criteria[-1].check_type == "semantic"
    assert events == ["contract_generation_started", "contract_generation_completed"]


def test_generator_requests_one_correction_for_an_unsafe_path():
    invalid = valid_contract_payload()
    invalid["criteria"][0]["path"] = "C:\\outside\\auth.py"
    client = SequenceClient([invalid, valid_contract_payload()])
    generator = StructuredGoalContractGenerator(client, max_attempts=2)
    goal = "Implement auth safely"

    contract = generator.generate(goal)

    assert contract.criteria[0].path == "src/auth.py"
    assert client.calls == 2
    assert "unsafe or missing relative path" in client.messages[1][-1]["content"]


def test_generator_fails_before_execution_after_two_invalid_contracts():
    invalid = valid_contract_payload()
    invalid["criteria"][1]["command"] = "powershell Remove-Item -Recurse ."
    client = SequenceClient([invalid, invalid])
    generator = StructuredGoalContractGenerator(client, max_attempts=2)

    try:
        generator.generate("Implement auth safely")
    except StructuredContractError as exc:
        assert "forbidden" in str(exc) or "not allowed" in str(exc)
    else:
        raise AssertionError("unsafe contract must not be returned")
    assert client.calls == 2


def test_contract_validator_rejects_duplicates_and_no_required_criteria():
    contract = AcceptanceContract(
        goal="goal",
        goal_summary="goal",
        criteria=[
            GoalCriterion("same", "one", "semantic", required=False),
            GoalCriterion("same", "two", "manual", required=False),
        ],
    )

    try:
        ContractValidator().validate(contract, expected_goal="goal")
    except ContractValidationError as exc:
        assert "duplicate criterion ids" in str(exc)
        assert "at least one required criterion" in str(exc)
    else:
        raise AssertionError("invalid contract should be rejected")


def test_contract_round_trip_preserves_summary_constraints_and_criteria():
    contract = AcceptanceContract(
        goal="goal",
        goal_summary="summary",
        criteria=[GoalCriterion("done", "done", "semantic")],
        constraints=["workspace only"],
    )

    restored = AcceptanceContract.from_dict(contract.to_dict())

    assert restored == contract


def test_contract_validator_rejects_type_coercion_from_model_json():
    contract = AcceptanceContract(
        goal="goal",
        goal_summary="summary",
        criteria=[GoalCriterion("done", "done", "semantic", required="true")],
    )

    try:
        ContractValidator().validate(contract, expected_goal="goal")
    except ContractValidationError as exc:
        assert "required must be boolean" in str(exc)
    else:
        raise AssertionError("string required flag should be rejected")
