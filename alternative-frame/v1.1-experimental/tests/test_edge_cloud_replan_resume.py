import json

from core.long_horizon import GoalEvaluation
from core.runtime_nodes import CloudNode, EdgeNode, NodeProbeResult, NodeStateStore
from run_edge_cloud_replan_demo import (
    EXPERIMENT_CRITERION,
    FALLBACK_CRITERION,
    RECOVERY_CRITERION,
    REPORT_CRITERION,
    contract_replan,
    run_demo,
)


def _sink(events):
    return lambda event, payload: events.append((event, payload))


def test_first_phase_is_rejected_by_contract(tmp_path):
    paused, _completed, _view, _run_dir = run_demo(tmp_path, "contract-first-phase")

    first = paused.state.phases[0].evaluation
    assert paused.state.acceptance_contract is not None
    assert first["completed"] is False
    assert set(first["missing_criteria"]) == {
        EXPERIMENT_CRITERION,
        FALLBACK_CRITERION,
        RECOVERY_CRITERION,
        REPORT_CRITERION,
    }


def test_replanner_maps_missing_criteria_to_routed_tasks():
    plan = contract_replan(
        None,
        GoalEvaluation(False, "missing", missing_criteria=[EXPERIMENT_CRITERION, FALLBACK_CRITERION]),
    )

    assert [task.id for task in plan.subtasks] == ["cloud_edge_fallback"]
    assert plan.subtasks[0].metadata["preferred_tier"] == "cloud"
    assert plan.subtasks[0].metadata["required_capabilities"] == ["compute"]


def test_final_completion_requires_all_contract_evidence(tmp_path):
    paused, completed, view, run_dir = run_demo(tmp_path, "contract-complete")

    assert paused.status == "paused"
    assert completed.status == "completed"
    assert completed.state.last_evaluation["missing_criteria"] == []
    assert set(completed.state.last_evaluation["satisfied_criteria"]) == {
        "device_sensitive_preprocess",
        EXPERIMENT_CRITERION,
        FALLBACK_CRITERION,
        RECOVERY_CRITERION,
        REPORT_CRITERION,
    }
    assert view["run_id"] == "contract-complete"
    assert (run_dir / "workspace" / "artifacts" / "final_report.json").is_file()


def test_stale_artifact_cannot_complete_contract(tmp_path):
    paused, _completed, _view, _run_dir = run_demo(
        tmp_path, "fresh-run", preseed_stale_artifacts=True
    )

    assert EXPERIMENT_CRITERION in paused.state.phases[0].evaluation["missing_criteria"]
    assert REPORT_CRITERION in paused.state.phases[0].evaluation["missing_criteria"]


def test_resume_current_probe_offline_routes_post_resume_task_to_edge(tmp_path):
    _paused, completed, _view, _run_dir = run_demo(
        tmp_path, "resume-offline", resume_cloud_online=False
    )
    row = next(
        record for record in completed.state.evidence_records
        if record.get("tool") == "runtime_executor"
        and record.get("task_id") == "post_resume_task"
        and record.get("success") is True
    )

    assert row["node_type"] == "edge"


def test_resume_current_probe_online_allows_post_resume_task_on_cloud(tmp_path):
    _paused, completed, _view, _run_dir = run_demo(
        tmp_path, "resume-online", resume_cloud_online=True
    )
    row = next(
        record for record in completed.state.evidence_records
        if record.get("tool") == "runtime_executor"
        and record.get("task_id") == "post_resume_task"
        and record.get("success") is True
    )

    assert row["node_type"] == "cloud"


def test_resume_probe_offline_overrides_online_snapshot(tmp_path):
    path = tmp_path / "node_state.json"
    NodeStateStore(path, run_id="probe").save([CloudNode("cloud-1", {"compute"})])
    events = []
    restored = NodeStateStore(
        path,
        run_id="probe",
        probe=lambda node: NodeProbeResult(False, False),
        on_event=_sink(events),
    ).prepare([CloudNode("cloud-1", {"compute"}), EdgeNode("edge-1", {"compute"})])

    cloud = next(node for node in restored if node.node_type == "cloud")
    assert cloud.online is False
    assert any(event == "node_state_changed" for event, _ in events)


def test_resume_probe_online_overrides_offline_snapshot(tmp_path):
    path = tmp_path / "node_state.json"
    offline = CloudNode("cloud-1", {"compute"}, online=False)
    NodeStateStore(path, run_id="probe").save([offline])
    events = []
    restored = NodeStateStore(
        path,
        run_id="probe",
        probe=lambda node: NodeProbeResult(True, True),
        on_event=_sink(events),
    ).prepare([CloudNode("cloud-1", {"compute"})])

    assert restored[0].online is True
    assert any(event == "node_state_changed" for event, _ in events)


def test_probe_failure_is_unknown_and_not_online(tmp_path):
    path = tmp_path / "node_state.json"
    NodeStateStore(path, run_id="probe").save([CloudNode("cloud-1", {"compute"})])
    events = []
    restored = NodeStateStore(
        path,
        run_id="probe",
        probe=lambda node: (_ for _ in ()).throw(TimeoutError("probe failed")),
        on_event=_sink(events),
    ).prepare([CloudNode("cloud-1", {"compute"})])

    assert restored[0].online is False
    assert restored[0].probe_status == "failed"
    reprobed = next(payload for event, payload in events if event == "node_state_reprobed")
    assert reprobed["probe_status"] == "failed"


def test_unchanged_probe_does_not_emit_changed_event(tmp_path):
    path = tmp_path / "node_state.json"
    NodeStateStore(path, run_id="probe").save([CloudNode("cloud-1", {"compute"})])
    events = []
    NodeStateStore(
        path,
        run_id="probe",
        probe=lambda node: NodeProbeResult(True, True),
        on_event=_sink(events),
    ).prepare([CloudNode("cloud-1", {"compute"})])

    assert any(event == "node_state_reprobed" for event, _ in events)
    assert not any(event == "node_state_changed" for event, _ in events)


def test_resume_does_not_repeat_frozen_successful_tasks(tmp_path):
    paused, completed, _view, _run_dir = run_demo(tmp_path, "no-repeat")
    before = list(paused.state.completed_tasks)

    assert before == ["phase-1:device_sensitive_preprocess", "phase-2:cloud_edge_fallback"]
    assert completed.state.completed_tasks.count("phase-1:device_sensitive_preprocess") == 1
    assert completed.state.completed_tasks.count("phase-2:cloud_edge_fallback") == 1
    assert "phase-3:post_resume_task" in completed.state.completed_tasks
    assert "phase-3:final_report" in completed.state.completed_tasks


def test_node_state_events_have_frozen_fields(tmp_path):
    _paused, _completed, _view, run_dir = run_demo(tmp_path, "event-fields")
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    state_events = [row for row in events if row["event"].startswith("node_state_")]
    assert {row["event"] for row in state_events} >= {
        "node_state_snapshot_saved",
        "node_state_reprobed",
        "node_state_changed",
    }
    required = {
        "run_id", "node_id", "node_type", "previous_online", "current_online",
        "previous_network_available", "current_network_available", "probe_status",
    }
    assert all(required <= set(row["payload"]) for row in state_events)
