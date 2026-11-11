"""Mock-only integration and ablation compatibility checks; no provider calls."""
import itertools
import json
from dataclasses import asdict

import pytest

from core.agents import Agent, AgentRegistry
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator
from core.experimental.runtime import PluginOptions, RuntimePlugins
from core.tool_calling_agent import ToolCallingAgent
from core.tools import ToolRegistry


class RecordingAgent(Agent):
    role = "worker"

    def __init__(self):
        self.tasks = []

    def run(self, task, context):
        self.tasks.append(task)
        return AgentResult(task.id, "success", summary="JSON schema validation persists verified experiment data")


def registry(agent):
    agents = AgentRegistry()
    agents.register(agent)
    return agents


@pytest.mark.parametrize("bits", list(itertools.product([False, True], repeat=4)))
def test_all_plugin_combinations_preserve_dag_and_deliver_selected_features(tmp_path, bits):
    options = PluginOptions(*bits)
    runtime = RuntimePlugins(options, tmp_path / "run", tmp_path, "goal")
    agent = RecordingAgent()
    plan = Plan("goal", [SubTask("prepare", "worker", "JSON schema validation"), SubTask("verify", "worker", "verify JSON schema validation", depends_on=["prepare"])])
    report = Orchestrator(registry(agent), plugins=runtime if options.enabled else None).run(plan)
    assert report.status == "success"
    assert len(agent.tasks) == 2
    payload = agent.tasks[-1].metadata.get("runtime_plugin_context", {})
    assert bool(payload.get("retrieved_memory")) == options.bm25
    assert bool(payload.get("dependency_messages")) == options.messages
    assert (runtime.root / "tasks.sqlite3").exists() == options.task_queue
    if runtime.queue:
        with runtime.queue._connect() as db:
            rows = db.execute("SELECT status, result FROM tasks").fetchall()
        assert len(rows) == 2
        assert all(row['status'] == "done" and json.loads(row['result'])["status"] == "success" for row in rows)
    runtime.observe_usage({"provider_usage_calls": 2, "total_tokens": 50})
    if runtime.audit:
        assert runtime.audit.snapshot()["total_tokens"] == 50
        runtime.observe_usage({"provider_usage_calls": 2, "total_tokens": 50})
        assert runtime.audit.snapshot()["total_tokens"] == 50
    assert plan.subtasks[-1].metadata == {}


def test_memory_survives_restart_rejects_stale_artifacts_and_isolates_runs(tmp_path):
    opts = PluginOptions(bm25=True)
    path = tmp_path / "output.txt"
    path.write_text("original")
    runtime = RuntimePlugins(opts, tmp_path / "r1", tmp_path, "goal")
    task = SubTask("a", "worker", "JSON import validation")
    runtime.run_task(task, {}, lambda t, c: (t, AgentResult(t.id, "success", "JSON import validation", artifacts=["output.txt"])))
    runtime.close()
    resumed = RuntimePlugins(opts, tmp_path / "r1", tmp_path, "goal")
    assert resumed.prepare_task(task, {}).metadata["runtime_plugin_context"]["retrieved_memory"]
    other = RuntimePlugins(opts, tmp_path / "r2", tmp_path, "goal")
    assert other.prepare_task(task, {}).metadata["runtime_plugin_context"]["retrieved_memory"] == []
    path.write_text("changed")
    assert resumed.prepare_task(task, {}).metadata["runtime_plugin_context"]["retrieved_memory"] == []
    with pytest.raises(ValueError, match="differs"):
        RuntimePlugins(PluginOptions(), tmp_path / "r1", tmp_path, "goal")
    with pytest.raises(ValueError, match="differs"):
        RuntimePlugins(opts, tmp_path / "r1", tmp_path, "other goal")


def test_actual_tool_agent_receives_memory_and_messages(tmp_path):
    class Client:
        def chat(self, messages, tools):
            self.payload = json.loads(messages[1]["content"])
            return {"content": "done"}
    client = Client()
    agent = ToolCallingAgent("worker", client, ToolRegistry([]), "Follow contract")
    runtime = RuntimePlugins(PluginOptions(bm25=True, messages=True), tmp_path / "run", tmp_path, "goal")
    seed = SubTask("first", "worker", "schema")
    result = AgentResult("first", "success", "schema accepted")
    runtime.run_task(seed, {}, lambda t, c: (t, result))
    task = SubTask("second", "worker", "schema", depends_on=["first"])
    report = Orchestrator(registry(agent), plugins=runtime).run(Plan("goal", [seed, task]), initial_results={"first": result})
    assert report.status == "success"
    context = client.payload["runtime_plugin_context"]
    assert context["retrieved_memory"]
    assert context["dependency_messages"][0]["task_id"] == "first"
    assert "override" in context["policy"]


def test_queue_interruption_releases_and_failed_result_is_not_success(tmp_path):
    runtime = RuntimePlugins(PluginOptions(task_queue=True), tmp_path / "run", tmp_path, "goal")
    task = SubTask("a", "worker", "task")
    def interrupt(*_):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        runtime.run_task(task, {}, interrupt)
    with runtime.queue._connect() as db:
        assert db.execute("SELECT status FROM tasks").fetchone()[0] == "pending"
    runtime.run_task(task, {}, lambda t, c: (t, AgentResult(t.id, "failed", failures=["bad"])))
    with runtime.queue._connect() as db:
        result = json.loads(db.execute("SELECT result FROM tasks WHERE status='done'").fetchone()[0])
    assert result["status"] == "failed"


def test_parallel_memory_records_are_complete_and_context_bounded(tmp_path):
    runtime = RuntimePlugins(PluginOptions(bm25=True, messages=True, task_queue=True), tmp_path / "run", tmp_path, "goal")
    agent = RecordingAgent()
    plan = Plan("goal", [SubTask(str(i), "worker", "JSON schema") for i in range(12)])
    assert Orchestrator(registry(agent), plugins=runtime).run(plan).status == "success"
    rows = [json.loads(line) for line in (runtime.root / "memory/events.jsonl").read_text().splitlines()]
    assert len(rows) == 12
    context = runtime.prepare_task(plan.subtasks[0], {}).metadata["runtime_plugin_context"]
    assert len(context["retrieved_memory"]) <= 3
    assert len(json.dumps(context["retrieved_memory"], ensure_ascii=False)) <= 4500


def test_invalid_configuration_and_secret_redaction(tmp_path):
    with pytest.raises(ValueError):
        PluginOptions.from_dict({"bm25": "yes"})
    runtime = RuntimePlugins(PluginOptions(bm25=True), tmp_path / "run", tmp_path, "goal")
    task = SubTask("a", "worker", "schema")
    secret = "sk-" + "A" * 24
    runtime.run_task(task, {}, lambda t, c: (t, AgentResult(t.id, "failed", summary=secret)))
    assert secret not in (runtime.root / "memory/events.jsonl").read_text()


def test_ui_selection_all_none_partial_and_busy_lock(monkeypatch):
    import tkinter as tk
    from tkinter import ttk
    from ui import FreshUI
    app = FreshUI()
    try:
        app.withdraw()
        app.show_plugin_options()
        app.update_idletasks()
        dialog = next(w for w in app.winfo_children() if isinstance(w, tk.Toplevel))
        def descendants(widget):
            return [child for w in widget.winfo_children() for child in [w, *descendants(w)]]
        widgets = descendants(dialog)
        buttons = {str(w.cget("text")): w for w in widgets if isinstance(w, ttk.Button)}
        checks = [w for w in widgets if isinstance(w, ttk.Checkbutton)]
        buttons["全选"].invoke()
        assert all(app.getvar(w.cget("variable")) for w in checks)
        buttons["全部关闭"].invoke()
        assert not any(app.getvar(w.cget("variable")) for w in checks)
        checks[0].invoke()
        buttons["应用"].invoke()
        assert app.plugin_options == PluginOptions(bm25=True)
        assert "BM25" in app.plugin_summary.get()
        app.running = True
        notices = []
        monkeypatch.setattr("ui.messagebox.showinfo", lambda *a, **k: notices.append(a))
        app.show_plugin_options()
        assert notices
        assert not any(isinstance(w, tk.Toplevel) for w in app.winfo_children())
    finally:
        app.destroy()


def test_usage_audit_resumed_totals_and_missing_usage_stay_distinct(tmp_path):
    runtime = RuntimePlugins(PluginOptions(usage_audit=True), tmp_path / "run", tmp_path, "goal")
    runtime.observe_usage({"provider_usage_calls": 234, "estimated_usage_calls": 0, "total_tokens": 3557108})
    runtime.observe_usage({"provider_usage_calls": 235, "estimated_usage_calls": 1, "total_tokens": 3557200})
    assert runtime.audit.snapshot()["total_tokens"] == 3557200
    rows = [json.loads(l) for l in (runtime.root / "audit/events.jsonl").read_text().splitlines()]
    last = rows[-1]["payload"]
    assert last["settled_calls"] == 236
    assert last["cost_usd"] is None
    with pytest.raises(ValueError, match="decreased"):
        runtime.observe_usage({"provider_usage_calls": 0, "total_tokens": 1})


def test_historical_export_uses_last_cumulative_snapshot_and_reports_mismatch(tmp_path):
    from scripts.export_api_baseline import summarize
    path = tmp_path / "api_usage.json"
    path.write_text(json.dumps({"run_id": "test", "sessions": [
        {"usage": {"total_tokens": 40}},
        {"status_at_save": "completed", "usage": {"total_tokens": 90, "requests": 2}},
    ]}))
    (tmp_path / "state.json").write_text(json.dumps({"status": "budget_exhausted", "goal": "goal"}))
    row = summarize(path)
    assert row["total_tokens"] == 90
    assert row["controller_status"] == "budget_exhausted"
    assert row["usage_status"] == "completed"
    assert row["cost_usd"] is None
    assert any("differs" in n for n in row["notes"])


def test_execution_metadata_records_source_hashes_not_credentials(tmp_path):
    from core.experimental.runtime import record_execution_metadata
    from core.model_client import ModelConfig
    tmp_path = tmp_path / "中文运行记录"
    tmp_path.mkdir()
    config = ModelConfig("https://example.invalid", "DO_NOT_SAVE", "model")
    record_execution_metadata(tmp_path, tmp_path, "goal", PluginOptions(), config, "API")
    record_execution_metadata(tmp_path, tmp_path, "goal", PluginOptions(), config, "API")
    raw = (tmp_path / "execution_metadata.json").read_text(encoding="utf-8")
    assert "DO_NOT_SAVE" not in raw
    data = json.loads(raw)
    assert len(data["sessions"]) == 2
    assert "core/experimental/runtime.py" in data["sessions"][0]["source_sha256"]


def test_completed_run_cannot_be_resumed(monkeypatch):
    from types import SimpleNamespace
    from ui import FreshUI
    app = FreshUI()
    try:
        notices = []
        monkeypatch.setattr("ui.messagebox.showinfo", lambda *a, **k: notices.append(a))
        app.resume_run(SimpleNamespace(status="completed"))
        assert notices
        assert not app.running
    finally:
        app.destroy()


def test_run_lock_blocks_second_owner_and_recovers_abandoned_queue_leases(tmp_path):
    options = PluginOptions(task_queue=True)
    first = RuntimePlugins(options, tmp_path / "run", tmp_path, "goal")
    ticket = first.queue.enqueue({"task_id": "old"})
    first.queue.claim_id(ticket, "worker")
    with pytest.raises(RuntimeError, match="already owns"):
        RuntimePlugins(options, tmp_path / "run", tmp_path, "goal")
    first.close()
    resumed = RuntimePlugins(options, tmp_path / "run", tmp_path, "goal")
    assert resumed.queue.get(ticket)["status"] == "pending"
    resumed.close()
