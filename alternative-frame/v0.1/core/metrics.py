from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

SCHEMA_VERSION = "1.1"
_UNKNOWN = None
_SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "access_token", "refresh_token",
    "token", "password", "secret", "client_secret", "cookie", "set-cookie",
}
_HUMAN_INTERVENTION_EVENTS = {
    "contract_modified", "acceptance_contract_modified", "manual_contract_edit",
    "run_paused", "manual_rerun", "human_rerun", "manual_resume",
}
_VALID_NODES = {"device", "edge", "cloud"}


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
    """Recursively redact credential-like fields before metrics persistence."""
    if isinstance(value, Mapping):
        sanitized: Dict[str, Any] = {}
        normalized_sensitive = {name.replace("-", "_") for name in _SENSITIVE_KEYS}
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in normalized_sensitive:
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = sanitize_sensitive(item)
        return sanitized
    if isinstance(value, (list, tuple)):
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
    device_failed_count: int = 0
    edge_failed_count: int = 0
    cloud_failed_count: int = 0
    unknown_node_failed_count: int = 0
    device_duration_seconds: Optional[float] = None
    edge_duration_seconds: Optional[float] = None
    cloud_duration_seconds: Optional[float] = None
    unknown_node_duration_seconds: Optional[float] = None
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
        return {"device": self.device_task_count, "edge": self.edge_task_count, "cloud": self.cloud_task_count, "unknown": self.unknown_node_task_count}

    @property
    def node_failures(self) -> Dict[str, int]:
        return {"device": self.device_failed_count, "edge": self.edge_failed_count, "cloud": self.cloud_failed_count, "unknown": self.unknown_node_failed_count}

    @property
    def node_durations(self) -> Dict[str, Optional[float]]:
        return {"device": self.device_duration_seconds, "edge": self.edge_duration_seconds, "cloud": self.cloud_duration_seconds, "unknown": self.unknown_node_duration_seconds}

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.update(
            subtask_success_rate=self.subtask_success_rate,
            first_pass_rate=self.first_pass_rate,
            tool_success_rate=self.tool_success_rate,
            node_distribution=self.node_distribution,
            node_failures=self.node_failures,
            node_durations=self.node_durations,
        )
        return sanitize_sensitive(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunMetrics":
        """Read legacy rows and current schema rows without mutating source history."""
        source = dict(data)
        allowed = {item.name for item in fields(cls)}
        source["tasks"] = [item if isinstance(item, TaskMetrics) else TaskMetrics(**item) for item in (source.get("tasks", []) or [])]
        source["calls"] = [item if isinstance(item, CallMetrics) else CallMetrics(**item) for item in (source.get("calls", []) or [])]
        source.setdefault("schema_version", "0.1")
        if source.get("schema_version") == "0.1":
            source.setdefault("metadata", {})
            source["metadata"] = dict(source["metadata"])
            source["metadata"].setdefault("legacy_token_zero_may_mean_unknown", True)
        return cls(**{key: value for key, value in source.items() if key in allowed})


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
    node_failures: Dict[str, int]
    node_durations: Dict[str, Optional[float]]


def _sum_optional(values: Iterable[Optional[float]]) -> Optional[float]:
    rows = list(values)
    known = [value for value in rows if value is not None]
    if not known:
        return None
    return round(sum(float(value) for value in known), 3)


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
    node_distribution = {key: sum(row.node_distribution[key] for row in rows) for key in ["device", "edge", "cloud", "unknown"]}
    node_failures = {key: sum(row.node_failures[key] for row in rows) for key in ["device", "edge", "cloud", "unknown"]}
    node_durations = {key: _sum_optional(row.node_durations[key] for row in rows) for key in ["device", "edge", "cloud", "unknown"]}
    return EvaluationSummary(
        run_count=len(rows), completed_run_count=completed_count,
        final_goal_completion_rate=_safe_rate(completed_count, len(completed_known)),
        task_count=task_count, success_count=success_count,
        subtask_success_rate=_safe_rate(success_count, task_count),
        first_pass_count=first_pass_count, first_pass_rate=_safe_rate(first_pass_count, task_count),
        retry_count=sum(row.retry_count for row in rows),
        local_recovery_count=sum(row.local_recovery_count for row in rows),
        additional_phase_count=sum(row.additional_phase_count for row in rows),
        mean_duration_seconds=round(sum(durations) / len(durations), 3) if durations else None,
        tool_calls=tool_calls, successful_tool_calls=successful_tool_calls,
        tool_success_rate=_safe_rate(successful_tool_calls, tool_calls),
        total_tokens=(sum(int(value) for value in token_values if value is not None) if rows and all(value is not None for value in token_values) else None),
        estimated_cost=(round(sum(float(value) for value in cost_values if value is not None), 8) if rows and all(value is not None for value in cost_values) else None),
        human_interventions=sum(row.human_interventions for row in rows),
        node_distribution=node_distribution, node_failures=node_failures, node_durations=node_durations,
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
    return (int(prompt) if prompt is not None else None, int(completion) if completion is not None else None, int(total) if total is not None else None)


def _node_from_task(task: Any, result: Any) -> str:
    metadata: Dict[str, Any] = {}
    metadata.update(getattr(task, "metadata", {}) or {})
    metadata.update(getattr(result, "metadata", {}) or {})
    raw = metadata.get("node") or metadata.get("execution_node") or metadata.get("deployment_target")
    normalized = str(raw).strip().lower() if raw is not None else "unknown"
    return normalized if normalized in _VALID_NODES else "unknown"


def _node_aggregates(tasks: Iterable[TaskMetrics]) -> tuple[Dict[str, int], Dict[str, int], Dict[str, Optional[float]]]:
    counts = {key: 0 for key in ["device", "edge", "cloud", "unknown"]}
    failures = {key: 0 for key in counts}
    duration_parts: Dict[str, List[float]] = {key: [] for key in counts}
    for task in tasks:
        node = task.node if task.node in _VALID_NODES else "unknown"
        counts[node] += 1
        if task.status != "success": failures[node] += 1
        if task.duration_seconds is not None: duration_parts[node].append(task.duration_seconds)
    durations = {key: (round(sum(values), 3) if values else None) for key, values in duration_parts.items()}
    return counts, failures, durations


def estimate_model_cost(prompt_tokens: Optional[int], completion_tokens: Optional[int], pricing: Mapping[str, Any] | None) -> Optional[float]:
    """Estimate cost from explicit per-million-token prices; otherwise unknown."""
    if prompt_tokens is None or completion_tokens is None or not pricing:
        return None
    try:
        input_rate = float(pricing["input_per_million"])
        output_rate = float(pricing["output_per_million"])
    except (KeyError, TypeError, ValueError):
        return None
    return round((prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000.0, 8)


def load_events(path: str | Path) -> List[Dict[str, Any]]:
    """Load valid append-only event records; malformed lines are ignored."""
    source = Path(path)
    if not source.is_file(): return []
    rows: List[Dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip(): continue
            try:
                row = json.loads(line)
                if isinstance(row, dict): rows.append(row)
            except json.JSONDecodeError:
                continue
    return rows


def count_human_interventions(events: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    for row in events:
        event = str(row.get("event", "")).strip().lower()
        payload = row.get("payload") if isinstance(row.get("payload"), Mapping) else {}
        if event in _HUMAN_INTERVENTION_EVENTS or payload.get("human_intervention") is True:
            count += 1
    return count


def metrics_from_report(report, domain: str, mode: str, model: str, started: float, run_id: str, metadata=None, plan=None, pricing=None) -> RunMetrics:
    values = list(report.results.values())
    plan_map = plan.task_map() if plan is not None and hasattr(plan, "task_map") else {}
    tasks: List[TaskMetrics] = []
    calls: List[CallMetrics] = []
    prompt_known: List[int] = []; completion_known: List[int] = []; total_known: List[int] = []
    any_usage_unknown = False
    for result in values:
        tool_records = list(getattr(result, "tool_records", []) or [])
        successful_tools = sum(record.get("success") is True for record in tool_records)
        model_call_count = sum(1 for evidence in getattr(result, "evidence", []) if evidence == "api_response_received" or str(evidence).startswith("model_step="))
        result_prompt: List[int] = []; result_completion: List[int] = []; result_total: List[int] = []
        for record in tool_records:
            prompt, completion, total = _usage_from_record(record)
            if prompt is not None: result_prompt.append(prompt)
            if completion is not None: result_completion.append(completion)
            if total is not None: result_total.append(total)
            calls.append(CallMetrics(
                call_type=str(record.get("call_type") or "tool"),
                name=str(record.get("tool") or record.get("name") or "unknown"),
                success=record.get("success") is True,
                duration_seconds=record.get("duration_seconds"),
                prompt_tokens=prompt, completion_tokens=completion, total_tokens=total,
                node=record.get("node"), metadata=sanitize_sensitive(record.get("metadata", {})),
            ))
        task_prompt = sum(result_prompt) if result_prompt else None
        task_completion = sum(result_completion) if result_completion else None
        task_total = sum(result_total) if result_total else None
        if model_call_count and task_total is None: any_usage_unknown = True
        if task_prompt is not None: prompt_known.append(task_prompt)
        if task_completion is not None: completion_known.append(task_completion)
        if task_total is not None: total_known.append(task_total)
        tasks.append(TaskMetrics(
            task_id=result.subtask_id, status=result.status, attempts=getattr(result, "attempts", 1),
            duration_seconds=_duration_seconds(getattr(result, "started_at", None), getattr(result, "finished_at", None)),
            node=_node_from_task(plan_map.get(result.subtask_id), result),
            tool_call_count=len(tool_records), successful_tool_calls=successful_tools,
            model_call_count=model_call_count, prompt_tokens=task_prompt, completion_tokens=task_completion, total_tokens=task_total,
        ))
    counts, failures, durations = _node_aggregates(tasks)
    model_calls = sum(task.model_call_count for task in tasks)
    token_unknown = any_usage_unknown or (model_calls > 0 and not total_known)
    prompt_tokens = None if token_unknown else sum(prompt_known)
    completion_tokens = None if token_unknown else sum(completion_known)
    total_tokens = None if token_unknown else sum(total_known)
    status = report.status
    return RunMetrics(
        run_id=run_id, domain=domain, mode=mode, model=model, status=status, rounds=report.rounds,
        task_count=len(values), success_count=sum(r.status == "success" for r in values), failed_count=sum(r.status != "success" for r in values),
        retry_count=sum(max(0, getattr(r, "attempts", 1) - 1) for r in values), duration_seconds=round(time.perf_counter() - started, 3),
        final_goal_completed=status in {"success", "completed"}, first_pass_count=sum(task.first_pass for task in tasks),
        local_recovery_count=int(getattr(report, "local_recovery_cycles", 0) or 0), phase_count=1, additional_phase_count=0,
        model_calls=model_calls, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens,
        estimated_cost=estimate_model_cost(prompt_tokens, completion_tokens, pricing),
        tool_calls=sum(task.tool_call_count for task in tasks), successful_tool_calls=sum(task.successful_tool_calls for task in tasks),
        device_task_count=counts["device"], edge_task_count=counts["edge"], cloud_task_count=counts["cloud"], unknown_node_task_count=counts["unknown"],
        device_failed_count=failures["device"], edge_failed_count=failures["edge"], cloud_failed_count=failures["cloud"], unknown_node_failed_count=failures["unknown"],
        device_duration_seconds=durations["device"], edge_duration_seconds=durations["edge"], cloud_duration_seconds=durations["cloud"], unknown_node_duration_seconds=durations["unknown"],
        tasks=tasks, calls=calls, metadata=sanitize_sensitive(metadata or {}),
    )


def metrics_from_long_horizon(state, phase_reports: Iterable[Any] | None = None, domain: str = "unknown", mode: str = "long_horizon", model: str = "unknown", events: Iterable[Mapping[str, Any]] | None = None, pricing=None) -> RunMetrics:
    reports = list(phase_reports or [])
    tasks: List[TaskMetrics] = []; calls: List[CallMetrics] = []
    prompt_known: List[int] = []; completion_known: List[int] = []; total_known: List[int] = []
    model_calls = 0; any_usage_unknown = False
    for report in reports:
        for result in report.results.values():
            records = list(getattr(result, "tool_records", []) or [])
            evidence = list(getattr(result, "evidence", []) or [])
            task_model_calls = sum(1 for item in evidence if item == "api_response_received" or str(item).startswith("model_step="))
            model_calls += task_model_calls
            rp: List[int] = []; rc: List[int] = []; rt: List[int] = []
            for record in records:
                prompt, completion, total = _usage_from_record(record)
                if prompt is not None: rp.append(prompt)
                if completion is not None: rc.append(completion)
                if total is not None: rt.append(total)
                calls.append(CallMetrics(str(record.get("call_type") or "tool"), str(record.get("tool") or record.get("name") or "unknown"), record.get("success") is True, record.get("duration_seconds"), prompt, completion, total, node=record.get("node"), metadata=sanitize_sensitive(record.get("metadata", {}))))
            if task_model_calls and not rt: any_usage_unknown = True
            prompt_known.extend(rp); completion_known.extend(rc); total_known.extend(rt)
            tasks.append(TaskMetrics(
                task_id=result.subtask_id, status=result.status, attempts=getattr(result, "attempts", 1),
                duration_seconds=_duration_seconds(getattr(result, "started_at", None), getattr(result, "finished_at", None)),
                node=_node_from_task(None, result), tool_call_count=len(records), successful_tool_calls=sum(record.get("success") is True for record in records),
                model_call_count=task_model_calls, prompt_tokens=sum(rp) if rp else None, completion_tokens=sum(rc) if rc else None, total_tokens=sum(rt) if rt else None,
            ))
    phase_count = len(getattr(state, "phases", []) or [])
    duration = _duration_seconds(getattr(state, "created_at", None), getattr(state, "updated_at", None)) or 0.0
    counts, failures, durations = _node_aggregates(tasks)
    token_unknown = any_usage_unknown or (model_calls > 0 and not total_known)
    prompt_tokens = None if token_unknown else sum(prompt_known)
    completion_tokens = None if token_unknown else sum(completion_known)
    total_tokens = None if token_unknown else sum(total_known)
    return RunMetrics(
        run_id=state.run_id, domain=domain, mode=mode, model=model, status=state.status, rounds=phase_count,
        task_count=len(tasks) if tasks else int(getattr(state, "total_tasks", 0)),
        success_count=sum(task.status == "success" for task in tasks) if tasks else len(getattr(state, "completed_tasks", []) or []),
        failed_count=sum(task.status != "success" for task in tasks) if tasks else len(getattr(state, "failed_tasks", []) or []),
        retry_count=sum(task.retry_count for task in tasks), duration_seconds=duration, final_goal_completed=state.status == "completed",
        first_pass_count=sum(task.first_pass for task in tasks),
        local_recovery_count=sum(int(getattr(phase, "local_recovery_cycles", 0) or 0) for phase in getattr(state, "phases", []) or []),
        phase_count=phase_count, additional_phase_count=max(phase_count - 1, 0), model_calls=model_calls,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens,
        estimated_cost=estimate_model_cost(prompt_tokens, completion_tokens, pricing),
        tool_calls=sum(task.tool_call_count for task in tasks), successful_tool_calls=sum(task.successful_tool_calls for task in tasks),
        human_interventions=count_human_interventions(events or []),
        device_task_count=counts["device"], edge_task_count=counts["edge"], cloud_task_count=counts["cloud"], unknown_node_task_count=(counts["unknown"] if tasks else int(getattr(state, "total_tasks", 0))),
        device_failed_count=failures["device"], edge_failed_count=failures["edge"], cloud_failed_count=failures["cloud"], unknown_node_failed_count=(failures["unknown"] if tasks else len(getattr(state, "failed_tasks", []) or [])),
        device_duration_seconds=durations["device"], edge_duration_seconds=durations["edge"], cloud_duration_seconds=durations["cloud"], unknown_node_duration_seconds=durations["unknown"],
        tasks=tasks, calls=calls, metadata={"source": "long_horizon_state"},
    )


class MetricsRecorder:
    def __init__(self, path: str | Path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, metrics: RunMetrics) -> None:
        line = json.dumps(metrics.to_dict(), ensure_ascii=False, allow_nan=False) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as stream: stream.write(line)
        except PermissionError:
            fallback = Path(r"C:\tmp\alternative-frame-v0.1-results.jsonl")
            try:
                fallback.parent.mkdir(parents=True, exist_ok=True)
                with fallback.open("a", encoding="utf-8") as stream: stream.write(line)
                print(f"warning: project results path is not writable; wrote metrics to {fallback}")
            except PermissionError:
                print("warning: metrics paths are not writable; metric_json=" + line.rstrip())

    def load(self) -> List[RunMetrics]: return load_metrics(self.path)


def load_metrics(path: str | Path) -> List[RunMetrics]:
    """Load valid rows from append-only JSONL; corrupt rows are skipped."""
    source = Path(path)
    if not source.is_file(): return []
    result: List[RunMetrics] = []
    with source.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip(): continue
            try:
                row = json.loads(line)
                if isinstance(row, Mapping): result.append(RunMetrics.from_dict(row))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    return result
