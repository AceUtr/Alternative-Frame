from run_deterministic_routing_ablation import run_mode


def test_fixed_cloud_fails_under_cloud_outage():
    result = run_mode("fixed_cloud")

    assert result.completed is False
    assert result.final_node_type == "cloud"
    assert result.fallback_count == 0
    assert result.execution_attempts == 1
    assert result.failed_attempts == 1

    assert result.cloud_attempts == 1
    assert result.edge_attempts == 0
    assert result.device_attempts == 0


def test_dynamic_routing_falls_back_to_edge():
    result = run_mode("dynamic_routing")

    assert result.completed is True
    assert result.final_node_type == "edge"

    assert result.fallback_count == 1
    assert result.execution_attempts == 2
    assert result.failed_attempts == 1

    assert result.cloud_attempts == 1
    assert result.edge_attempts == 1
    assert result.device_attempts == 0


def test_dynamic_routing_changes_final_outcome():
    fixed = run_mode("fixed_cloud")
    dynamic = run_mode("dynamic_routing")

    assert fixed.completed is False
    assert dynamic.completed is True

    assert fixed.fallback_count == 0
    assert dynamic.fallback_count == 1


def test_dynamic_routing_preserves_failure_trace():
    result = run_mode("dynamic_routing")

    assert len(result.tool_records) == 2

    first, second = result.tool_records

    assert first["node_type"] == "cloud"
    assert first["success"] is False

    assert second["node_type"] == "edge"
    assert second["success"] is True
