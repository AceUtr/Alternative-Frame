from ui_components.metrics_views import (
    agent_summary,
    contract_summary,
    format_overview_text,
    overview_cards,
    recovery_summary,
    routing_summary,
)


def _payload():
    return {
        "agent_speedup": 1.245,
        "routing_result": {
            "fixed_cloud_completed": False,
            "dynamic_completed": True,
            "dynamic_final_node": "edge",
            "fallback_count": 1,
        },
        "rows": [
            {
                "experiment": "agent_topology",
                "condition": "single_agent",
                "completed": True,
                "mean_duration_seconds": 0.404,
            },
            {
                "experiment": "agent_topology",
                "condition": "multi_agent",
                "completed": True,
                "mean_duration_seconds": 0.324,
            },
            {
                "experiment": "local_recovery",
                "condition": "recovery_off",
                "completed": False,
                "result": "failure remained failed",
            },
            {
                "experiment": "local_recovery",
                "condition": "recovery_on",
                "completed": True,
                "result": "recovery restored success",
            },
            {
                "experiment": "contract_validation",
                "condition": "contract_off",
                "completed": True,
                "result": "false completion accepted",
            },
            {
                "experiment": "contract_validation",
                "condition": "contract_on",
                "completed": False,
                "result": "missing evidence detected",
            },
            {
                "experiment": "routing",
                "condition": "fixed_cloud",
                "completed": False,
                "result": "cloud outage caused failure",
            },
            {
                "experiment": "routing",
                "condition": "dynamic_routing",
                "completed": True,
                "result": "cloud to edge fallback",
            },
        ],
    }


def test_agent_view_exposes_speedup():
    result = agent_summary(_payload())

    assert result["wall_clock_speedup"] == 1.245


def test_recovery_view_preserves_ablation_result():
    result = recovery_summary(_payload())

    assert result["off_completed"] is False
    assert result["on_completed"] is True


def test_contract_view_preserves_false_completion_result():
    result = contract_summary(_payload())

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


def test_routing_view_preserves_cloud_edge_fallback():
    result = routing_summary(_payload())

    assert result["fixed_completed"] is False
    assert result["dynamic_completed"] is True
    assert result["dynamic_final_node"] == "edge"
    assert result["fallback_count"] == 1


def test_overview_cards_include_all_four_ablations():
    cards = overview_cards(_payload())

    values = {
        card["title"]: card["value"]
        for card in cards
    }

    assert values["Local Recovery"] == "PASS"
    assert values["Contract Gate"] == "PASS"
    assert values["Dynamic Routing"] == "PASS"

    assert (
        values["Multi-Agent Speedup"]
        == "1.245x"
    )


def test_overview_text_is_readable():
    text = format_overview_text(_payload())

    assert "Multi-Agent Speedup" in text
    assert "Local Recovery" in text
    assert "Contract Gate" in text
    assert "Dynamic Routing" in text
