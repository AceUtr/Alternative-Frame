import json
from pathlib import Path

from reports.generate_unified_evaluation import latest


def test_required_benchmark_evidence_exists():
    research = latest(
        "research_recorded-*.json"
    )
    recovery = latest(
        "deterministic_recovery-*.json"
    )
    contract = latest(
        "deterministic_contract-*.json"
    )

    assert research.exists()
    assert recovery.exists()
    assert contract.exists()


def test_recovery_ablation_has_expected_controlled_result():
    path = latest(
        "deterministic_recovery-*.json"
    )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    rows = {
        row["mode"]: row
        for row in payload["results"]
    }

    assert rows["recovery_off"]["goal_completed"] is False
    assert rows["recovery_on"]["goal_completed"] is True

    assert (
        rows["recovery_off"]["local_recovery_count"]
        == 0
    )

    assert (
        rows["recovery_on"]["local_recovery_count"]
        == 1
    )

    assert rows["recovery_on"]["execution_log"] == [
        "prepare",
        "compute",
        "compute",
        "verify",
    ]


def test_contract_ablation_has_single_missing_gate():
    path = latest(
        "deterministic_contract-*.json"
    )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    rows = {
        row["mode"]: row
        for row in payload["results"]
    }

    assert rows["contract_off"]["completed"] is True
    assert rows["contract_on"]["completed"] is False

    assert rows["contract_on"]["satisfied_criteria"] == [
        "source",
        "tests",
    ]

    assert rows["contract_on"]["missing_criteria"] == [
        "final_evidence",
    ]


def test_recorded_research_is_not_relabelled_as_controlled():
    path = latest(
        "research_recorded-*.json"
    )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert (
        payload["evidence_kind"]
        == "recorded_real_run"
    )
