from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping


RUNTIME_TELEMETRY_SCHEMA_VERSION = "1.0"
RUNTIME_EVENT_NAMES = (
    "placement_decided",
    "node_execution_started",
    "node_execution_failed",
    "node_fallback_started",
    "node_execution_completed",
)


def aggregate_runtime_metrics(records: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Aggregate stable C/D metrics from runtime_executor tool records."""
    rows = [dict(row) for row in records if row.get("tool") == "runtime_executor"]
    node_types = ("device", "edge", "cloud", "unknown")
    distribution = {name: 0 for name in node_types}
    duration = {name: 0.0 for name in node_types}
    failures = {name: 0 for name in node_types}
    max_fallback_by_task: Dict[str, int] = {}
    completed_tasks = set()
    no_eligible = 0

    for row in rows:
        node_type = str(row.get("node_type") or row.get("node") or "unknown").lower()
        if node_type not in duration:
            node_type = "unknown"
        duration[node_type] += float(row.get("duration") or row.get("duration_seconds") or 0.0)
        task_id = str(row.get("task_id") or "unknown")
        fallback_count = int(row.get("fallback_count") or 0)
        max_fallback_by_task[task_id] = max(max_fallback_by_task.get(task_id, 0), fallback_count)
        if row.get("success") is False:
            failures[node_type] += 1
        if row.get("failure_kind") == "no_eligible_node":
            no_eligible += 1
        if row.get("success") is True and task_id not in completed_tasks:
            distribution[node_type] += 1
            completed_tasks.add(task_id)

    return {
        "schema_version": RUNTIME_TELEMETRY_SCHEMA_VERSION,
        "node_distribution": distribution,
        "node_duration_seconds": {
            key: round(value, 6) for key, value in duration.items()
        },
        "node_failure_count": failures,
        "fallback_count": sum(max_fallback_by_task.values()),
        "execution_attempt_count": len(rows),
        "no_eligible_node_count": no_eligible,
    }


__all__ = [
    "RUNTIME_EVENT_NAMES",
    "RUNTIME_TELEMETRY_SCHEMA_VERSION",
    "aggregate_runtime_metrics",
]
