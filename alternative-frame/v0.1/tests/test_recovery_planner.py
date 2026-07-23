from core.long_horizon import (
    AcceptanceContract,
    DeterministicRecoveryPlanner,
    GoalCriterion,
    GoalEvaluation,
    LongHorizonState,
    ResilientReplanner,
)


def recovery_state():
    contract = AcceptanceContract(
        "goal",
        [
            GoalCriterion("source", "source", "file_exists", path="app.py"),
            GoalCriterion("tests", "tests", "file_exists", path="test_app.py"),
            GoalCriterion("docs", "docs", "file_exists", path="README.md"),
        ],
        goal_summary="goal",
    )
    return LongHorizonState(
        "run",
        "goal",
        3,
        10,
        phase=1,
        total_tasks=2,
        acceptance_contract=contract.to_dict(),
    )


def test_deterministic_recovery_only_plans_missing_criteria():
    state = recovery_state()
    evaluation = GoalEvaluation(False, "missing", missing_criteria=["tests", "docs"])

    plan = DeterministicRecoveryPlanner()(state, evaluation)

    owned = {
        item
        for task in plan.subtasks
        for item in task.metadata["contract_criteria"]
    }
    assert owned == {"tests", "docs"}
    assert all("app.py" not in task.metadata["expected_outputs"] for task in plan.subtasks)


def test_resilient_replanner_uses_rules_when_primary_times_out():
    state = recovery_state()
    evaluation = GoalEvaluation(False, "missing", missing_criteria=["docs"])
    events = []

    def timeout(_state, _evaluation):
        raise TimeoutError("read operation timed out")

    plan = ResilientReplanner(
        timeout,
        on_event=lambda event, payload: events.append(event),
    )(state, evaluation)

    assert [item for task in plan.subtasks for item in task.metadata["contract_criteria"]] == ["docs"]
    assert events == ["replan_fallback_started", "replan_fallback_completed"]
