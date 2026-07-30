from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

SCHEMA_VERSION = "1.0"
_UNKNOWN = None
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "client_secret",
    "cookie",
    "set-cookie",
}


def _safe_rate(numerator: int | float, denominator: int | float) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 6)


def _parse_iso(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _duration_seconds(started_at: str | None, finished_at: str | None) -> Optional[float]:
    start = _parse_iso(started_at)
    end = _parse_iso(finished_at)
    if not start or not end:
        return None
    seconds = (end - start).total_seconds()
    return round(seconds, 3) if seconds >= 0 else None


def sanitize_sensitive(value: Any) -> Any:
    """Recursively remove credential-like fields before metrics persistence."""
    if isinstance(value, Mapping):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in {name.replace("-", "_") for name in _SENSITIVE_KEYS}:
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = sanitize_sensitive(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_sensitive(item) for item in value]
    return value


@dataclass
class CallMetrics:
    call_type: str
    name: str
    success: bool
    duration_seconds: Optional[float] = None
    prompt_tokens: Optional[int] = _UNKNOWN
    completion_tokens: Optional[int] = _UNKNOWN
    total_tokens: Optional[int] = _UNKNOWN
    estimated_cost: Optional[float] = _UNKNOWN
    node: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskMetrics:
    task_id: str
    status: str
    attempts: int = 1
    duration_seconds: Optional[float] = None
    node: Optional[str] = None
    tool_call_count: int = 0
    successful_tool_calls: int = 0
    model_call_count: int = 0
    prompt_tokens: Optional[int] = _UNKNOWN
    completion_tokens: Optional[int] = _UNKNOWN
    total_tokens: Optional[int] = _UNKNOWN
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def retry_count(self) -> int:
        return max(self.attempts - 1, 0)

    @property
    def first_pass(self) -> bool:
        return self.status == "success" and self.retry_count == 0


@dataclass
class RunMetrics:
    run_id: str
    domain: str
    mode: str
    model: str
    status: str
    rounds: int
    task_count: int
    success_count: int
    failed_count: int
    retry_count: int
    duration_seconds: float
    schema_version: str = SCHEMA_VERSION
    final_goal_completed: Optional[bool] = None
    first_pass_count: int = 0
    local_recovery_count: int = 0
    phase_count: int = 1
    additional_phase_count: int = 0
    model_calls: int = 0
    prompt_tokens: Optional[int] = _UNKNOWN
    completion_tokens: Optional[int] = _UNKNOWN
    total_tokens: Optional[int] = _UNKNOWN
    estimated_cost: Optional[float] = _UNKNOWN
    tool_calls: int = 0
    successful_tool_calls: int = 0
    human_interventions: int = 0
    device_task_count: int = 0
    edge_task_count: int = 0
    cloud_task_count: int = 0
    unknown_node_task_count: int = 0
    tasks: List[TaskMetrics] = field(default_factory=list)
    calls: List[CallMetrics] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def subtask_success_rate(self) -> Optional[float]:
        return _safe_rate(self.success_count, self.task_count)

    @property
    def first_pass_rate(self) -> Optional[float]:
        return _safe_rate(self.first_pass_count, self.task_count)

    @property
    def tool_success_rate(self) -> Optional[float]:
        return _safe_rate(self.successful_tool_calls, self.tool_calls)

    @property
    def node_distribution(self) -> Dict[str, int]:
        return {
            "device": self.device_task_count,
            "edge": self.edge_task_count,
            "cloud": self.cloud_task_count,
            "unknown": self.unknown_node_task_count,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["subtask_success_rate"] = self.subtask_success_rate
        data["first_pass_rate"] = self.first_pass_rate
        data["tool_success_rate"] = self.tool_success_rate
        data["node_distribution"] = self.node_distribution
        return sanitize_sensitive(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunMetrics":
        """Read both legacy results.jsonl rows and schema v1 rows."""
        source = dict(data)
        allowed = {item.name for item in fields(cls)}
        task_rows = source.get("tasks", []) or []
        call_rows = source.get("calls", []) or []
        source["tasks"] = [item if isinstance(item, TaskMetrics) else TaskMetrics(**item) for item in task_rows]
        source["calls"] = [item if isinstance(item, CallMetrics) else CallMetrics(**item) for item in call_rows]
        source.setdefault("schema_version", "0.1")
        # Legacy rows used integer zero for unknown token usage. Preserve the row,
        # while marking the ambiguity in metadata rather than silently rewriting it.
        if source.get("schema_version") == "0.1":
            source.setdefault("metadata", {})
            source["metadata"] = dict(source["metadata"])
            source["metadata"].setdefault("legacy_token_zero_may_mean_unknown", True)
        filtered = {key: value for key, value in source.items() if key in allowed}
        return cls(**filtered)


@dataclass
class EvaluationSummary:
    run_count: int
    completed_run_count: int
    final_goal_completion_rate: Optional[float]
    task_count: int
    success_count: int
    subtask_success_rate: Optional[float]
    first_pass_count: int
    first_pass_rate: Optional[float]
    retry_count: int
    local_recovery_count: int
    additional_phase_count: int
    mean_duration_seconds: Optional[float]
    tool_calls: int
    successful_tool_calls: int
    tool_success_rate: Optional[float]
    total_tokens: Optional[int]
    estimated_cost: Optional[float]
    human_interventions: int
    node_distribution: Dict[str, int]


def summarize_metrics(runs: Iterable[RunMetrics]) -> EvaluationSummary:
    rows = list(runs)
    completed_known = [row for row in rows if row.final_goal_completed is not None]
    completed_count = sum(row.final_goal_completed is True for row in completed_known)
    durations = [row.duration_seconds for row in rows if row.duration_seconds is not None and row.duration_seconds >= 0]
    token_values = [row.total_tokens for row in rows]
    cost_values = [row.estimated_cost for row in rows]

    task_count = sum(row.task_count for row in rows)
    success_count = sum(row.success_count for row in rows)
    first_pass_count = sum(row.first_pass_count for row in rows)
    tool_calls = sum(row.tool_calls for row in rows)
    successful_tool_calls = sum(row.successful_tool_calls for row in rows)

    node_distribution = {"device": 0, "edge": 0, "cloud": 0, "unknown": 0}
    for row in rows:
        for key, value in row.node_distribution.items():
            node_distribution[key] += value

    return EvaluationSummary(
        run_count=len(rows),
        completed_run_count=completed_count,
        final_goal_completion_rate=_safe_rate(completed_count, len(completed_known)),
        task_count=task_count,
        success_count=success_count,
        subtask_success_rate=_safe_rate(success_count, task_count),
        first_pass_count=first_pass_count,
        first_pass_rate=_safe_rate(first_pass_count, task_count),
        retry_count=sum(row.retry_count for row in rows),
        local_recovery_count=sum(row.local_recovery_count for row in rows),
        additional_phase_count=sum(row.additional_phase_count for row in rows),
        mean_duration_seconds=round(sum(durations) / len(durations), 3) if durations else None,
        tool_calls=tool_calls,
        successful_tool_calls=successful_tool_calls,
        tool_success_rate=_safe_rate(successful_tool_calls, tool_calls),
        total_tokens=(sum(int(value) for value in token_values if value is not None) if rows and all(value is not None for value in token_values) else None),
        estimated_cost=(round(sum(float(value) for value in cost_values if value is not None), 8) if rows and all(value is not None for value in cost_values) else None),
        human_interventions=sum(row.human_interventions for row in rows),
        node_distribution=node_distribution,
    )


def _usage_from_record(record: Mapping[str, Any]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    usage = record.get("usage") or record.get("metadata", {}).get("usage") or {}
    if not isinstance(usage, Mapping) or not usage:
        return None, None, None
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    total = usage.get("total_tokens")
    if total is None and prompt is not None and completion is not None:
        total = int(prompt) + int(completion)
    return (
        int(prompt) if prompt is not None else None,
        int(completion) if completion is not None else None,
        int(total) if total is not None else None,
    )


def _node_from_task(task: Any, result: Any) -> str:
    metadata = {}
    metadata.update(getattr(task, "metadata", {}) or {})
    metadata.update(getattr(result, "metadata", {}) or {})
    raw = metadata.get("node") or metadata.get("execution_node") or metadata.get("deployment_target")
    normalized = str(raw).strip().lower() if raw is not None else "unknown"
    return normalized if normalized in {"device", "edge", "cloud"} else "unknown"


def metrics_from_report(report, domain: str, mode: str, model: str, started: float, run_id: str, metadata=None) -> RunMetrics:
    values = list(report.results.values())
    plan_map = {}
    tasks: List[TaskMetrics] = []
    calls: List[CallMetrics] = []
    prompt_known: List[int] = []
    completion_known: List[int] = []
    total_known: List[int] = []
    any_usage_unknown = False

    for result in values:
        tool_records = list(getattr(result, "tool_records", []) or [])
        successful_tools = sum(record.get("success") is True for record in tool_records)
        model_call_count = sum(
            1
            for evidence in getattr(result, "evidence", [])
            if evidence == "api_response_received" or str(evidence).startswith("model_step=")
        )
        result_prompt: List[int] = []
        result_completion: List[int] = []
        result_total: List[int] = []
        for record in tool_records:
            prompt, completion, total = _usage_from_record(record)
            if total is None:
                continue
            if prompt is not None:
                result_prompt.append(prompt)
            if completion is not None:
                result_completion.append(completion)
            result_total.append(total)
            calls.append(
                CallMetrics(
                    call_type=str(record.get("call_type") or "tool"),
                    name=str(record.get("tool") or record.get("name") or "unknown"),
                    success=record.get("success") is True,
                    duration_seconds=record.get("duration_seconds"),
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=total,
                    node=record.get("node"),
                    metadata=sanitize_sensitive(record.get("metadata", {})),
                )
            )
        task_prompt = sum(result_prompt) if result_prompt else None
        task_completion = sum(result_completion) if result_completion else None
        task_total = sum(result_total) if result_total else None
        if task_total is None and model_call_count:
            any_usage_unknown = True
        else:
            if task_prompt is not None:
                prompt_known.append(task_prompt)
            if task_completion is not None:
                completion_known.append(task_completion)
            if task_total is not None:
                total_known.append(task_total)
        tasks.append(
            TaskMetrics(
                task_id=result.subtask_id,
                status=result.status,
                attempts=getattr(result, "attempts", 1),
                duration_seconds=_duration_seconds(getattr(result, "started_at", None), getattr(result, "finished_at", None)),
                node=_node_from_task(plan_map.get(result.subtask_id), result),
                tool_call_count=len(tool_records),
                successful_tool_calls=successful_tools,
                model_call_count=model_call_count,
                prompt_tokens=task_prompt,
                completion_tokens=task_completion,
                total_tokens=task_total,
            )
        )

    node_counts = {"device": 0, "edge": 0, "cloud": 0, "unknown": 0}
    for task in tasks:
        node_counts[task.node or "unknown"] += 1

    model_calls = sum(task.model_call_count for task in tasks)
    token_unknown = any_usage_unknown or (model_calls > 0 and not total_known)
    status = report.status
    return RunMetrics(
        run_id=run_id,
        domain=domain,
        mode=mode,
        model=model,
        status=status,
        rounds=report.rounds,
        task_count=len(values),
        success_count=sum(result.status == "success" for result in values),
        failed_count=sum(result.status != "success" for result in values),
        retry_count=sum(max(0, getattr(result, "attempts", 1) - 1) for result in values),
        duration_seconds=round(time.perf_counter() - started, 3),
        final_goal_completed=status in {"success", "completed"},
        first_pass_count=sum(task.first_pass for task in tasks),
        local_recovery_count=int(getattr(report, "local_recovery_cycles", 0) or 0),
        phase_count=1,
        additional_phase_count=0,
        model_calls=model_calls,
        prompt_tokens=None if token_unknown else sum(prompt_known),
        completion_tokens=None if token_unknown else sum(completion_known),
        total_tokens=None if token_unknown else sum(total_known),
        tool_calls=sum(task.tool_call_count for task in tasks),
        successful_tool_calls=sum(task.successful_tool_calls for task in tasks),
        device_task_count=node_counts["device"],
        edge_task_count=node_counts["edge"],
        cloud_task_count=node_counts["cloud"],
        unknown_node_task_count=node_counts["unknown"],
        tasks=tasks,
        calls=calls,
        metadata=sanitize_sensitive(metadata or {}),
    )


def metrics_from_long_horizon(state, phase_reports: Iterable[Any] | None = None, domain: str = "unknown", mode: str = "long_horizon", model: str = "unknown") -> RunMetrics:
    reports = list(phase_reports or [])
    tasks: List[TaskMetrics] = []
    for report in reports:
        for result in report.results.values():
            records = list(getattr(result, "tool_records", []) or [])
            tasks.append(
                TaskMetrics(
                    task_id=result.subtask_id,
                    status=result.status,
                    attempts=getattr(result, "attempts", 1),
                    duration_seconds=_duration_seconds(getattr(result, "started_at", None), getattr(result, "finished_at", None)),
                    node="unknown",
                    tool_call_count=len(records),
                    successful_tool_calls=sum(record.get("success") is True for record in records),
                )
            )
    phase_count = len(getattr(state, "phases", []) or [])
    duration = _duration_seconds(getattr(state, "created_at", None), getattr(state, "updated_at", None)) or 0.0
    node_counts = {"device": 0, "edge": 0, "cloud": 0, "unknown": len(tasks)}
    return RunMetrics(
        run_id=state.run_id,
        domain=domain,
        mode=mode,
        model=model,
        status=state.status,
        rounds=phase_count,
        task_count=len(tasks) if tasks else int(getattr(state, "total_tasks", 0)),
        success_count=sum(task.status == "success" for task in tasks) if tasks else len(getattr(state, "completed_tasks", []) or []),
        failed_count=sum(task.status != "success" for task in tasks) if tasks else len(getattr(state, "failed_tasks", []) or []),
        retry_count=sum(task.retry_count for task in tasks),
        duration_seconds=duration,
        final_goal_completed=state.status == "completed",
        first_pass_count=sum(task.first_pass for task in tasks),
        local_recovery_count=sum(int(getattr(phase, "local_recovery_cycles", 0) or 0) for phase in getattr(state, "phases", []) or []),
        phase_count=phase_count,
        additional_phase_count=max(phase_count - 1, 0),
        tool_calls=sum(task.tool_call_count for task in tasks),
        successful_tool_calls=sum(task.successful_tool_calls for task in tasks),
        unknown_node_task_count=node_counts["unknown"],
        tasks=tasks,
        metadata={"source": "long_horizon_state"},
    )


class MetricsRecorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, metrics: RunMetrics) -> None:
        line = json.dumps(metrics.to_dict(), ensure_ascii=False, allow_nan=False) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line)
        except PermissionError:
            fallback = Path(r"C:\tmp\alternative-frame-v0.1-results.jsonl")
            try:
                fallback.parent.mkdir(parents=True, exist_ok=True)
                with fallback.open("a", encoding="utf-8") as stream:
                    stream.write(line)
                print(f"warning: project results path is not writable; wrote metrics to {fallback}")
            except PermissionError:
                print("warning: metrics paths are not writable; metric_json=" + line.rstrip())

    def load(self) -> List[RunMetrics]:
        return load_metrics(self.path)


def load_metrics(path: str | Path) -> List[RunMetrics]:
    """Load valid rows from append-only JSONL; corrupt rows are skipped."""
    source = Path(path)
    if not source.is_file():
        return []
    result: List[RunMetrics] = []
    with source.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if isinstance(row, Mapping):
                    result.append(RunMetrics.from_dict(row))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    return result
