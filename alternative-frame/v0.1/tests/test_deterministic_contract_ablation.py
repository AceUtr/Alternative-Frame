from run_deterministic_contract_ablation import run_mode


def test_contract_off_accepts_successful_phase_report():
    result = run_mode("contract_off")

    assert result.phase_report_status == "success"
    assert result.completed is True
    assert result.missing_criteria == []


def test_contract_on_rejects_only_missing_final_evidence():
    result = run_mode("contract_on")

    assert result.phase_report_status == "success"
    assert result.completed is False

    # Proven controls must pass.
    assert "source" in result.satisfied_criteria
    assert "tests" in result.satisfied_criteria

    # The intentionally omitted final artifact is the only missing gate.
    assert result.missing_criteria == [
        "final_evidence"
    ]


def test_contract_prevents_false_completion():
    off = run_mode("contract_off")
    on = run_mode("contract_on")

    # Identical green phase report.
    assert off.phase_report_status == "success"
    assert on.phase_report_status == "success"

    # Only the completion policy changes.
    assert off.completed is True
    assert on.completed is False

    assert on.satisfied_criteria == [
        "source",
        "tests",
    ]

    assert on.missing_criteria == [
        "final_evidence"
    ]
