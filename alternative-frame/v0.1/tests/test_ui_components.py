from ui_components.metrics_views import (
    agent_summary,
    contract_summary,
    format_overview_text,
    overview_cards,
    recovery_summary,
)


def _payload():
    return {
        "live_llm_available": False,
        "rows": [
            {
                "experiment": "agent_topology",
                "condition": "single_agent",
                "goal_completion_rate": 1.0,
                "mean_duration_seconds": 0.4048,
                "parallel_overlap_seconds": 0.0,
                "unique_backend_count": 1,
                "key_result": "single shared backend",
            },
            {
                "experiment": "agent_topology",
                "condition": "multi_agent",
                "goal_completion_rate": 1.0,
                "mean_duration_seconds": 0.3244,
                "parallel_overlap_seconds": 0.0803,
                "unique_backend_count": 5,
                "key_result": (
                    "1.248x wall-clock speedup"
                ),
            },
            {
                "experiment": "local_recovery",
                "condition": "recovery_off",
                "goal_completion_rate": 0,
                "key_result": (
                    "injected failure remained failed"
                ),
            },
            {
                "experiment": "local_recovery",
                "condition": "recovery_on",
                "goal_completion_rate": 1,
                "key_result": (
                    "one local recovery cycle restored success"
                ),
            },
            {
                "experiment": "contract_validation",
                "condition": "contract_off",
                "goal_completion_rate": 1,
                "key_result": (
                    "false completion accepted"
                ),
            },
            {
                "experiment": "contract_validation",
                "condition": "contract_on",
                "goal_completion_rate": 0,
                "key_result": (
                    "missing final_evidence correctly rejected"
                ),
            },
        ],
    }


def test_agent_view_exposes_speedup():
    result = agent_summary(
        _payload()
    )

    assert result["single_completion_rate"] == 1.0
    assert result["multi_completion_rate"] == 1.0

    assert result["wall_clock_speedup"] is not None
    assert result["wall_clock_speedup"] > 1.0

    assert result["single_backend_count"] == 1
    assert result["multi_backend_count"] == 5


def test_recovery_view_preserves_ablation_result():
    result = recovery_summary(
        _payload()
    )

    assert result["off_completed"] is False
    assert result["on_completed"] is True


def test_contract_view_preserves_false_completion_result():
    result = contract_summary(
        _payload()
    )

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


def test_overview_cards_are_available_without_generated_report():
    cards = overview_cards(
        _payload()
    )

    assert len(cards) >= 4

    values = {
        card["title"]: card["value"]
        for card in cards
    }

    assert "Multi-Agent Speedup" in values
    assert values["Local Recovery"] == "PASS"
    assert values["Contract Gate"] == "PASS"


def test_overview_text_is_readable():
    text = format_overview_text(
        _payload()
    )

    assert "Multi-Agent Speedup" in text
    assert "Local Recovery" in text
    assert "Contract Gate" in text
