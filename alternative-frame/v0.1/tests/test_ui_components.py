import json
from pathlib import Path

from ui_components.metrics_views import (
    agent_summary,
    contract_summary,
    format_overview_text,
    load_competition_evaluation,
    overview_cards,
    recovery_summary,
)


REPORT = Path(
    "reports/unified_evaluation_v2/"
    "competition_evaluation.json"
)


def test_competition_evaluation_can_be_loaded():
    payload = load_competition_evaluation(
        REPORT
    )

    assert "rows" in payload


def test_agent_view_exposes_speedup():
    payload = load_competition_evaluation(
        REPORT
    )

    result = agent_summary(payload)

    assert (
        result["single_completion_rate"]
        == 1.0
    )

    assert (
        result["multi_completion_rate"]
        == 1.0
    )

    assert (
        result["wall_clock_speedup"]
        is not None
    )

    assert (
        result["wall_clock_speedup"]
        > 1.0
    )


def test_recovery_view_preserves_ablation_result():
    payload = load_competition_evaluation(
        REPORT
    )

    result = recovery_summary(payload)

    assert result["off_completed"] is False
    assert result["on_completed"] is True


def test_contract_view_preserves_false_completion_result():
    payload = load_competition_evaluation(
        REPORT
    )

    result = contract_summary(payload)

    assert (
        result[
            "without_contract_declared_complete"
        ]
        is True
    )

    assert (
        result[
            "with_contract_declared_complete"
        ]
        is False
    )


def test_overview_text_is_readable():
    payload = load_competition_evaluation(
        REPORT
    )

    cards = overview_cards(payload)
    text = format_overview_text(payload)

    assert len(cards) >= 4
    assert "Multi-Agent Speedup" in text
    assert "Local Recovery" in text
    assert "Contract Gate" in text
