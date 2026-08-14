import json
from pathlib import Path

from reports.generate_real_evaluation import (
    enrich_row,
    latest_recorded_summary,
)


def test_latest_real_evaluation_summary_exists():
    path = latest_recorded_summary(
        Path("benchmarks/results/summary")
    )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert payload["evidence_kind"] == "recorded_real_run"
    assert len(payload["runs"]) == 2


def test_real_evaluation_preserves_recovery_semantics():
    path = latest_recorded_summary(
        Path("benchmarks/results/summary")
    )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

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

    assert normal["contract_first_phase_pass"] is False
    assert recovery["contract_first_phase_pass"] is False

    assert normal["final_contract_pass"] is True
    assert recovery["final_contract_pass"] is True


def test_unknown_usage_is_not_converted_to_zero():
    path = latest_recorded_summary(
        Path("benchmarks/results/summary")
    )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    for raw in payload["runs"]:
        row = enrich_row(raw)

        assert row["prompt_tokens"] is None
        assert row["completion_tokens"] is None
        assert row["total_tokens"] is None
        assert row["estimated_cost"] is None
