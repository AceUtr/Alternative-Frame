from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping

from core.metrics import RunMetrics


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _duration_seconds(started_at: str | None, finished_at: str | None) -> float:
    started = _parse_iso(started_at)
    finished = _parse_iso(finished_at)
    if started is None or finished is None:
        return 0.0
    return max((finished - started).total_seconds(), 0.0)


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    source = Path(path)

    if not source.exists():
        return records

    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)

    return records


def _event_count(events: List[Mapping[str, Any]], event_name: str) -> int:
    return sum(1 for item in events if item.get("event") == event_name)


def _first_pass_success_count(events: List[Mapping[str, Any]]) -> int:
    first_result: Dict[str, str] = {}

    for item in events:
        if item.get("event") != "task_finished":
            continue

        payload = item.get("payload") or {}
        task_id = str(payload.get("task_id") or "")
        status = str(payload.get("status") or "")

        if task_id and task_id not in first_result:
            first_result[task_id] = status

    return sum(status == "success" for status in first_result.values())


def _human_interventions(events: List[Mapping[str, Any]]) -> int:
    intervention_events = {
        "human_intervention",
        "human_override",
        "manual_intervention",
        "manual_override",
        "user_intervention",
    }
    return sum(1 for item in events if item.get("event") in intervention_events)


def metrics_from_recorded_run(
    run_dir: str | Path,
    *,
    domain: str = "research",
    mode: str = "recorded_real_run",
    model: str = "unknown",
) -> RunMetrics:
    run_path = Path(run_dir)

    state = json.loads(
        (run_path / "state.json").read_text(encoding="utf-8")
    )
    events = load_jsonl(run_path / "events.jsonl")

    phases = list(state.get("phases") or [])
    evidence_records = list(state.get("evidence_records") or [])

    task_finished = [
        item
        for item in events
        if item.get("event") == "task_finished"
    ]

    observed_failed_executions = sum(
        1
        for item in task_finished
        if (item.get("payload") or {}).get("status") != "success"
    )

    successful_tool_calls = sum(
        1
        for record in evidence_records
        if record.get("success") is True
    )

    phase_count = len(phases)

    # IMPORTANT:
    # The supplied real research fixture explicitly says model token/usage
    # was not collected. Missing usage is unknown, not numeric zero.
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    estimated_cost = None

    metadata = {
        "source": "recorded_long_horizon_run",
        "evidence_kind": "recorded_real_run",
        "state_path": str(run_path / "state.json"),
        "events_path": str(run_path / "events.jsonl"),
        "token_usage_status": "unknown",
        "cost_status": "unknown",
        "artifact_count": len(state.get("artifacts") or []),
        "event_count": len(events),
        "observed_task_finished_count": len(task_finished),
        "observed_failed_executions": observed_failed_executions,
        "phase_statuses": [
            {
                "number": phase.get("number"),
                "status": phase.get("status"),
                "local_recovery_cycles": phase.get(
                    "local_recovery_cycles", 0
                ),
            }
            for phase in phases
        ],
    }

    return RunMetrics(
        run_id=str(state.get("run_id") or run_path.name),
        domain=domain,
        mode=mode,
        model=model,
        status=str(state.get("status") or "unknown"),
        rounds=phase_count,
        task_count=int(state.get("total_tasks") or 0),
        success_count=len(state.get("completed_tasks") or []),
        failed_count=len(state.get("failed_tasks") or []),
        retry_count=_event_count(events, "task_retry_scheduled"),
        duration_seconds=_duration_seconds(
            state.get("created_at"),
            state.get("updated_at"),
        ),
        schema_version="1.1",
        final_goal_completed=state.get("status") == "completed",
        first_pass_count=_first_pass_success_count(events),
        local_recovery_count=_event_count(
            events, "local_recovery_started"
        ),
        phase_count=phase_count,
        additional_phase_count=max(phase_count - 1, 0),
        model_calls=0,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=estimated_cost,
        tool_calls=len(evidence_records),
        successful_tool_calls=successful_tool_calls,
        human_interventions=_human_interventions(events),

        # No device/edge/cloud assignment exists in this historical fixture.
        # Keep tasks in the explicit unknown bucket.
        device_task_count=0,
        edge_task_count=0,
        cloud_task_count=0,
        unknown_node_task_count=int(state.get("total_tasks") or 0),

        device_failed_count=0,
        edge_failed_count=0,
        cloud_failed_count=0,
        unknown_node_failed_count=len(state.get("failed_tasks") or []),

        device_duration_seconds=None,
        edge_duration_seconds=None,
        cloud_duration_seconds=None,
        unknown_node_duration_seconds=None,

        tasks=[],
        calls=[],
        metadata=metadata,
    )
