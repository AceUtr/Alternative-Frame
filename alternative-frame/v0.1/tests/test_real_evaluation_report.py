import json
from pathlib import Path

from core.recorded_metrics import metrics_from_recorded_run
from reports.generate_real_evaluation import enrich_row


FIXTURE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "research_evaluation"
)


def _build_recorded_payload():
    rows = []

    for case_name, fixture_name, mode in [
        ("research_normal", "normal", "normal"),
        (
            "research_local_recovery",
            "local_recovery",
            "local_recovery",
        ),
    ]:
        metrics = metrics_from_recorded_run(
            FIXTURE_ROOT / fixture_name,
            domain="research",
            mode=mode,
        )

        rows.append(
            {
                "case": case_name,
                "run_id": metrics.run_id,
                "evidence_kind": "recorded_real_run",
                "status": metrics.status,
                "final_goal_completed": (
                    metrics.final_goal_completed
                ),
                "task_count": metrics.task_count,
                "success_count": metrics.success_count,
                "failed_count": metrics.failed_count,
                "first_pass_count": metrics.first_pass_count,
                "retry_count": metrics.retry_count,
                "local_recovery_count": (
                    metrics.local_recovery_count
                ),
                "phase_count": metrics.phase_count,
                "duration_seconds": (
                    metrics.duration_seconds
                ),
                "tool_calls": metrics.tool_calls,
                "successful_tool_calls": (
                    metrics.successful_tool_calls
                ),
                "tool_success_rate": (
                    metrics.tool_success_rate
                ),
                "prompt_tokens": metrics.prompt_tokens,
                "completion_tokens": (
                    metrics.completion_tokens
                ),
                "total_tokens": metrics.total_tokens,
                "estimated_cost": metrics.estimated_cost,
            }
        )

    return {
        "benchmark": "research_recorded",
        "evidence_kind": "recorded_real_run",
        "runs": rows,
    }


def test_real_evaluation_preserves_recovery_semantics():
    payload = _build_recorded_payload()

    rows = {
        item["case"]: enrich_row(item)
        for item in payload["runs"]
    }

    normal = rows["research_normal"]
    recovery = rows["research_local_recovery"]

    assert normal["goal_completed"] is True
    assert recovery["goal_completed"] is True

    assert normal["completed_tasks"] == 8
    assert recovery["completed_tasks"] == 8

    assert normal["cumulative_planned_tasks"] == 8
    assert recovery["cumulative_planned_tasks"] == 11

    assert normal["extra_planned_tasks"] == 0
    assert recovery["extra_planned_tasks"] == 3

    assert normal["local_recovery_count"] == 0
    assert recovery["local_recovery_count"] == 1

    assert normal["first_pass_count"] == 8
    assert recovery["first_pass_count"] == 7


def test_unknown_usage_is_not_converted_to_zero():
    payload = _build_recorded_payload()

    for raw in payload["runs"]:
        row = enrich_row(raw)

        assert row["prompt_tokens"] is None
        assert row["completion_tokens"] is None
        assert row["total_tokens"] is None
        assert row["estimated_cost"] is None


def test_recorded_payload_is_explicitly_real_evidence():
    payload = _build_recorded_payload()

    assert payload["evidence_kind"] == "recorded_real_run"

    assert {
        item["case"]
        for item in payload["runs"]
    } == {
        "research_normal",
        "research_local_recovery",
    }
