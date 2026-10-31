from core.routing import TaskRequirements
from core.runtime_nodes import CloudNode, EdgeNode, RuntimeExecutor


def _execute_with_failure(mode):
    events = []
    executor = RuntimeExecutor(on_event=lambda event, payload: events.append((event, payload)))
    result = executor.execute(
        TaskRequirements(
            task_id=f"dynamic-{mode}",
            required_capabilities={"compute"},
            preferred_tier="cloud",
        ),
        [
            CloudNode("cloud-1", {"compute"}, execution_failure_mode=mode),
            EdgeNode("edge-1", {"compute"}),
        ],
        lambda node: f"completed on {node.node_id}",
    )
    return result, events


def test_node_goes_offline_and_falls_back_to_edge():
    result, events = _execute_with_failure("offline")

    assert result.success is True
    assert result.selected_node_id == "edge-1"
    assert result.tool_records[0]["failure_kind"] == "node_offline"
    assert any(event == "node_fallback_started" for event, _ in events)


def test_network_interruption_and_falls_back_to_edge():
    result, _events = _execute_with_failure("network")

    assert result.success is True
    assert result.selected_node_id == "edge-1"
    assert result.tool_records[0]["failure_kind"] == "network_interrupted"


def test_timeout_and_falls_back_to_edge():
    result, _events = _execute_with_failure("timeout")

    assert result.success is True
    assert result.selected_node_id == "edge-1"
    assert result.tool_records[0]["failure_kind"] == "timeout"


def test_no_eligible_node_has_complete_evidence_and_failure_event():
    events = []
    result = RuntimeExecutor(
        on_event=lambda event, payload: events.append((event, payload))
    ).execute(
        TaskRequirements(task_id="no-node", required_capabilities={"gpu"}),
        [EdgeNode("edge-1", {"inference"}, online=False)],
        lambda node: node.node_id,
    )

    assert result.success is False
    record = result.tool_records[0]
    assert record["failure_kind"] == "no_eligible_node"
    for field in ("node_id", "node_type", "placement_reason", "duration", "fallback_count"):
        assert field in record
    assert [event for event, _ in events] == ["placement_decided", "node_execution_failed"]


def test_required_runtime_event_sequence_is_persistable():
    result, events = _execute_with_failure("offline")

    assert result.success is True
    assert [event for event, _ in events] == [
        "placement_decided",
        "node_execution_started",
        "node_execution_failed",
        "node_fallback_started",
        "node_execution_started",
        "node_execution_completed",
    ]
    for event, payload in events:
        if event.startswith("node_execution_"):
            for field in ("node_id", "node_type", "placement_reason", "duration", "fallback_count"):
                if event == "node_execution_started" and field == "duration":
                    continue
                assert field in payload
