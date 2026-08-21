from pathlib import Path

from core.recorded_metrics import metrics_from_recorded_run
from run_deterministic_contract_ablation import (
    run_mode as run_contract_mode,
)
from run_deterministic_recovery_ablation import (
    run_mode as run_recovery_mode,
)


FIXTURE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "research_evaluation"
)


def test_recovery_ablation_has_expected_controlled_result():
    off = run_recovery_mode("recovery_off")
    on = run_recovery_mode("recovery_on")

    assert off.goal_completed is False
    assert on.goal_completed is True

    assert off.local_recovery_count == 0
    assert on.local_recovery_count == 1

    assert on.execution_log == [
        "prepare",
        "compute",
        "compute",
        "verify",
    ]


def test_contract_ablation_has_single_missing_gate():
    off = run_contract_mode("contract_off")
    on = run_contract_mode("contract_on")

    assert off.completed is True
    assert on.completed is False

    assert on.satisfied_criteria == [
        "source",
        "tests",
    ]

    assert on.missing_criteria == [
        "final_evidence",
    ]


def test_recorded_research_is_not_relabelled_as_controlled():
    normal = metrics_from_recorded_run(
        FIXTURE_ROOT / "normal"
    )

    recovery = metrics_from_recorded_run(
        FIXTURE_ROOT / "local_recovery"
    )

    assert (
        normal.metadata["evidence_kind"]
        == "recorded_real_run"
    )

    assert (
        recovery.metadata["evidence_kind"]
        == "recorded_real_run"
    )


def test_recorded_and_controlled_evidence_are_distinct():
    recorded = metrics_from_recorded_run(
        FIXTURE_ROOT / "normal"
    )

    controlled = run_recovery_mode(
        "recovery_on"
    )

    assert (
        recorded.metadata["evidence_kind"]
        == "recorded_real_run"
    )

    assert (
        controlled.evidence_kind
        == "deterministic_controlled_run"
    )
