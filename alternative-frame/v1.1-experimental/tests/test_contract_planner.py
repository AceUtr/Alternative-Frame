from core.long_horizon import (
    AcceptanceContract,
    ContractAwarePlanner,
    ContractCoverageError,
    ContractCoverageValidator,
    GoalCriterion,
)
from core.models import Plan, SubTask


def baseline():
    return Plan(
        "build service",
        [
            SubTask(
                "develop",
                "developer",
                "implement service",
                metadata={
                    "required_tools": ["file_editor"],
                    "expected_outputs": ["src/"],
                    "checks": [{"id": "base_source", "check_type": "file_exists"}],
                },
            ),
            SubTask(
                "verify",
                "tester",
                "test service",
                depends_on=["develop"],
                metadata={
                    "required_tools": ["test_runner"],
                    "expected_outputs": ["tests/"],
                    "checks": [{"id": "base_tests", "check_type": "file_exists"}],
                },
            ),
        ],
    )


def contract():
    return AcceptanceContract(
        "build service",
        [
            GoalCriterion("source", "source exists", "file_exists", path="src/app.py"),
            GoalCriterion("tests", "tests pass", "command", command="python -m pytest -q"),
            GoalCriterion("docs", "API documentation exists", "file_exists", path="README.md"),
        ],
        goal_summary="build and verify a documented service",
    )


def test_contract_planner_assigns_every_required_criterion():
    plan = ContractAwarePlanner().build(contract(), baseline())

    owners = {
        criterion_id: task.id
        for task in plan.subtasks
        for criterion_id in task.metadata["contract_criteria"]
    }
    assert set(owners) == {"source", "tests", "docs"}
    assert plan.final_acceptance == ["source", "tests", "docs"]
    assert owners["source"] == "develop"
    assert owners["tests"] == "verify"


def test_contract_coverage_validator_rejects_an_unowned_required_criterion():
    plan = baseline()
    for task in plan.subtasks:
        task.metadata["contract_criteria"] = []

    try:
        ContractCoverageValidator().validate(plan, contract())
    except ContractCoverageError as exc:
        assert "source" in str(exc)
    else:
        raise AssertionError("missing contract coverage must be rejected")
