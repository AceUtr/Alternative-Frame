"""Read-only historical API evidence export. Does not contact providers."""
from pathlib import Path
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(path, snapshot_dir=None):
    buffers = {}
    def read_json(source):
        buffers[source] = source.read_bytes()
        return json.loads(buffers[source].decode("utf-8"))
    data = read_json(path)
    sessions = data.get("sessions", [])
    if not sessions:
        return None
    last = sessions[-1]
    usage = last.get("usage", {})
    state_path = path.parent / "state.json"
    report_path = path.parent / "run_report.json"
    state = read_json(state_path) if state_path.exists() else {}
    report = read_json(report_path) if report_path.exists() else {}
    events_path = path.parent / "events.jsonl"
    events, invalid_lines = [], 0
    if events_path.exists():
        buffers[events_path] = events_path.read_bytes()
        for line in buffers[events_path].decode("utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                invalid_lines += 1
    tool_events = [e for e in events if e.get("event") == "tool_finished"]
    config_path = path.parent / "plugins/config.json"
    options = read_json(config_path)["options"] if config_path.exists() else None
    provenance = path.parent / "execution_metadata.json"
    metadata = read_json(provenance) if provenance.exists() else {}
    goal = state.get("goal", report.get("goal"))
    model_result = state.get("last_evaluation") or {}
    notes = []
    if not state and not report:
        notes.append("No persisted controller state/final report; usage status alone does not establish active execution or completion.")
    if not metadata:
        notes.append("Historical code commit/configuration provenance missing; current HEAD must not be substituted.")
    if not usage.get("provider_usage_calls", last.get("provider_usage_calls", 0)) and not usage.get("estimated_usage_calls", 0):
        notes.append("No settled response usage is recorded; recorded zero tokens is not proof of zero billable usage.")
    if state.get("status") and state.get("status") != last.get("status_at_save"):
        notes.append("Controller state differs from latest API usage snapshot; report both rather than treating old usage status as current completion.")
    if options is None:
        notes.append("Plugin manifest absent. Code inspection established old main UI did not integrate these plugins; per-run configuration unrecorded.")
    if data.get("run_id") == "c97d17f0cc0b":
        notes += ["Independent product check: 25 tests passed and 18 reported file hashes matched on 2026-11-05; this does not validate later workspace changes.", "Browser interaction acceptance not established; generated FINAL_EVIDENCE API-zero statement describes neither framework usage nor known cost."]
    sources = [p for p in [path, state_path, report_path, events_path, config_path, provenance] if p.exists()]
    source_records = []
    def redact(value):
        if isinstance(value, dict):
            return {k: "<redacted>" if re.search(r"(?i)(api[_ -]?key|authorization|password|secret|access[_ -]?token)", k) else redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v) for v in value]
        if isinstance(value, str):
            return re.sub(r"sk-[A-Za-z0-9_-]{16,}|(?i:Bearer)\s+[A-Za-z0-9._-]+", "<redacted>", value)
        return value
    for source in sources:
        raw = buffers[source]
        record = {"path": str(source.resolve()), "sha256": hashlib.sha256(raw).hexdigest()}
        if snapshot_dir is not None:
            folder = Path(snapshot_dir) / path.parent.name
            folder.mkdir(parents=True, exist_ok=True)
            saved = folder / (source.name + ".snapshot.json")
            value = {"valid_events": events, "invalid_line_count": invalid_lines} if source == events_path else json.loads(raw.decode("utf-8"))
            saved.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2), encoding="utf-8")
            record.update(snapshot=str(saved.resolve()), snapshot_sha256=digest(saved))
        source_records.append(record)
    return {
        "run_id": data.get("run_id", path.parent.name), "goal_summary": (goal or "")[:120],
        "goal_sha256": hashlib.sha256(goal.encode()).hexdigest() if goal else None,
        "controller_status": state.get("status", report.get("status")), "usage_status": last.get("status_at_save"),
        "phase": state.get("phase"), "task_count": state.get("total_tasks"),
        "last_error": state.get("last_error"), "model": last.get("model"),
        "recorded_at": last.get("recorded_at"), "logical_requests": usage.get("requests"),
        "transport_attempts": usage.get("transport_attempts"),
        "total_tokens": usage.get("total_tokens"), "provider_usage_calls": usage.get("provider_usage_calls", last.get("provider_usage_calls")),
        "estimated_usage_calls": usage.get("estimated_usage_calls"),
        "unconfirmed_reserved_tokens": usage.get("unconfirmed_reserved_tokens"),
        "elapsed_seconds": usage.get("elapsed_seconds"), "limits": last.get("limits"),
        "semantic_evaluator_completed": model_result.get("completed"),
        "accepted_phase_history": [{"number": p.get("number"), "finished_at": p.get("finished_at")} for p in state.get("phases", []) if p.get("status") == "accepted"],
        "controller_updated_at": state.get("updated_at"),
        "observed_task_retry_events": sum(e.get("event") == "task_retry_scheduled" for e in events),
        "observed_tool_finished_events": len(tool_events),
        "observed_tool_failure_events": sum(e.get("payload", {}).get("success") is False for e in tool_events),
        "invalid_event_lines": invalid_lines, "plugin_options": options,
        "actual_execution_metadata": metadata, "cost_usd": None, "cost_status": "unknown",
        "notes": notes, "sources": source_records,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, default=Path(__file__).resolve().parents[1] / "runs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, errors = [], []
    for path in sorted(args.runs.rglob("api_usage.json")):
        try:
            row = summarize(path, args.output / "snapshots")
            if row:
                rows.append(row)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append({"path": str(path.resolve()), "error_type": type(exc).__name__})
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "historical_api_baseline.json"
    target.write_text(json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "evidence_kind": "historical_live_api_records", "method": "Latest cumulative snapshot per run, never sum resumed sessions. Observed event counts may be incomplete. No causal plugin uplift can be inferred.", "runs": rows, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# 历史真实 API 基线（非插件效果对照）", "", "每个运行取最后一份累计快照，不累加恢复前后 sessions；费用统一 unknown。状态采用原始记录，不把模型判定等同独立验收。旧运行未记录的 commit 和插件配置保持未知。", "", "| Run ID | 控制器状态 | 用量快照状态 | 请求数 | Tokens | 秒 | 阶段 |", "|---|---|---|---:|---:|---:|---:|"]
    for row in rows:
        md.append("| " + " | ".join(str(row.get(k)) if row.get(k) is not None else "unknown" for k in ["run_id", "controller_status", "usage_status", "logical_requests", "total_tokens", "elapsed_seconds", "phase"]) + " |")
    md += ["", "## 来源及限制", ""]
    for row in rows:
        md += ["### " + row["run_id"], ""] + ["- " + n for n in row["notes"]] + ["- 来源：`" + s["path"] + "`；SHA-256：`" + s["sha256"] + "`；脱敏快照：`" + s.get("snapshot", "unknown") + "`" for s in row["sources"]] + [""]
    md += ["## 后续对照要求", "", "同一修复版本、同一模型/服务线路、相同目标与验收合同、相同预算和工具条件、独立空目录、相同数据种子。至少设置全部关闭、仅 BM25、全部启用三组，每组建议至少 3 次；记录失败和人工干预，不挑最好的一次。历史不同任务与不同代码结果仅提供背景，不能直接算插件提升率。", "", "主指标：独立合同验收通过率；辅助指标：首次通过率、重试/重复工具失败、模型请求、usage 来源、耗时、人工干预。队列 done 只表示处理完成，不代表任务成功。"]
    (args.output / "HISTORICAL_API_BASELINE.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"runs": len(rows), "errors": len(errors), "json": str(target.resolve())}))


if __name__ == "__main__":
    main()
