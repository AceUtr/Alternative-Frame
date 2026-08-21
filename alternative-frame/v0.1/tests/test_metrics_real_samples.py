from pathlib import Path

from core.recorded_metrics import metrics_from_recorded_run


FIXTURE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "research_evaluation"
)


def test_recorded_research_normal_metrics():
    metrics = metrics_from_recorded_run(
        FIXTURE_ROOT / "normal"
    )

    assert metrics.run_id == "research-normal-20260812"
    assert metrics.status == "completed"
    assert metrics.final_goal_completed is True

    assert metrics.phase_count == 2
    assert metrics.additional_phase_count == 1

    assert metrics.task_count == 8
    assert metrics.success_count == 8
    assert metrics.failed_count == 0

    assert metrics.first_pass_count == 8
    assert metrics.retry_count == 0
    assert metrics.local_recovery_count == 0

    assert metrics.tool_calls == 8
    assert metrics.successful_tool_calls == 8

    assert metrics.prompt_tokens is None
    assert metrics.completion_tokens is None
    assert metrics.total_tokens is None
    assert metrics.estimated_cost is None

    assert metrics.metadata["evidence_kind"] == "recorded_real_run"
    assert metrics.metadata["token_usage_status"] == "unknown"


def test_recorded_research_local_recovery_metrics():
    metrics = metrics_from_recorded_run(
        FIXTURE_ROOT / "local_recovery"
    )

    assert metrics.run_id == "research-local-recovery-20260812"
    assert metrics.status == "completed"
    assert metrics.final_goal_completed is True

    assert metrics.phase_count == 2
    assert metrics.additional_phase_count == 1

    # total_tasks includes recovery-plan work in the persisted state.
    assert metrics.task_count == 11

    # Eight unique final tasks are recorded as completed.
    assert metrics.success_count == 8
    assert metrics.failed_count == 0

    # run_improved failed its first observed execution before local recovery.
    assert metrics.first_pass_count == 7

    assert metrics.retry_count == 0
    assert metrics.local_recovery_count == 1

    assert metrics.tool_calls == 8
    assert metrics.successful_tool_calls == 8

    assert metrics.prompt_tokens is None
    assert metrics.completion_tokens is None
    assert metrics.total_tokens is None
    assert metrics.estimated_cost is None

    assert metrics.metadata["observed_failed_executions"] == 1
    assert metrics.metadata["evidence_kind"] == "recorded_real_run"


def test_recorded_contract_requires_second_phase():
    normal = metrics_from_recorded_run(
        FIXTURE_ROOT / "normal"
    )
    recovery = metrics_from_recorded_run(
        FIXTURE_ROOT / "local_recovery"
    )

    for metrics in (normal, recovery):
        statuses = metrics.metadata["phase_statuses"]

        assert statuses[0]["number"] == 1
        assert statuses[0]["status"] == "incomplete"

        assert statuses[1]["number"] == 2
        assert statuses[1]["status"] == "accepted"
