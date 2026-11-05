"""Local fault-injection checks. No provider network or credentials are used."""
import io
import json
import sys
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.agents import Agent, AgentRegistry, DeterministicAgent
from core.long_horizon import GoalEvaluation, LongHorizonController, LongHorizonState, LongHorizonStore
from core.long_horizon.state import plan_to_dict
from core.local_recovery import LocalDAGRecoveryController
from core.model_client import ModelCallBudget, ModelConfig, OpenAICompatibleClient
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator
from core.tool_calling_agent import ToolCallingAgent
from core.tools import FileEditor, ShellRunner, ToolRegistry
from ui import FreshUI, load_api_usage_totals, save_api_usage_evidence


class Response:
    status = 200

    def __init__(self, usage=None):
        self.usage = {"total_tokens": 40} if usage is None else usage

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps({"choices": [{"message": {"content": "done"}}], "usage": self.usage}).encode()


@pytest.mark.parametrize("headers,body,expected", [
    ({"Retry-After": "23"}, "", 23),
    ({}, "All accounts rate-limited. Cooldown wait 23s.", 23),
    ({"Retry-After": "invalid"}, "Cooldown wait 2.5s", 2.5),
    ({"Retry-After": "900"}, "", 900),
])
def test_cooldown_parser(headers, body, expected):
    assert OpenAICompatibleClient._retry_delay(headers, body, 1) == expected


def test_503_waits_for_provider_then_succeeds(monkeypatch):
    outcomes = [urllib.error.HTTPError("https://example.test/v1", 503, "busy", {}, io.BytesIO(b"All accounts rate-limited. Cooldown wait 23s.")), Response()]
    waits = []
    def request(*_, **__):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    monkeypatch.setattr("core.model_client.urllib.request.urlopen", request)
    monkeypatch.setattr("core.model_client.time.sleep", waits.append)
    client = OpenAICompatibleClient(ModelConfig("https://example.test/v1", "unused", "fake"))
    assert client.chat([{"role": "user", "content": "work"}])["content"] == "done"
    assert len(waits) == 1 and 22 < waits[0] <= 23
    assert client.budget_snapshot()["transport_attempts"] == 2


def test_cooldown_does_not_outlive_run_budget(monkeypatch):
    calls = []
    def request(*_, **__):
        calls.append(1)
        raise urllib.error.HTTPError("https://example.test/v1", 429, "busy", {"Retry-After": "23"}, io.BytesIO(b"busy"))
    monkeypatch.setattr("core.model_client.urllib.request.urlopen", request)
    monkeypatch.setattr("core.model_client.time.sleep", lambda _: pytest.fail("must not sleep past budget"))
    client = OpenAICompatibleClient(ModelConfig("https://example.test/v1", "unused", "fake", max_runtime_seconds=10))
    with pytest.raises(RuntimeError, match="cooldown"):
        client.chat([{"role": "user", "content": "work"}])
    assert len(calls) == 1
    assert client.budget_snapshot()["in_flight_reserved_tokens"] == 0


@pytest.mark.parametrize("usage", [{}, {"total_tokens": -1}, {"total_tokens": "invalid"}])
def test_invalid_usage_is_estimated_instead_of_zero_or_negative(monkeypatch, usage):
    monkeypatch.setattr("core.model_client.urllib.request.urlopen", lambda *_, **__: Response(usage))
    client = OpenAICompatibleClient(ModelConfig("https://example.test/v1", "unused", "fake"))
    client.chat([{"role": "user", "content": "work"}])
    assert client.budget_snapshot()["total_tokens"] > 0
    assert client.budget_snapshot()["estimated_usage_calls"] == 1
    assert client.budget_snapshot()["provider_usage_calls"] == 0


def test_each_api_call_is_checkpointed_before_and_after(monkeypatch, tmp_path):
    path = tmp_path / "api_usage.json"
    config = ModelConfig("https://example.test/v1", "never-save", "fake")
    client = OpenAICompatibleClient(config)
    client.on_budget_update = lambda _: save_api_usage_evidence(path, "run", client, config, "running", checkpoint=True)
    def request(*_, **__):
        saved = load_api_usage_totals(path)
        assert saved["requests"] == 1
        assert saved["in_flight_reserved_tokens"] > 0
        return Response()
    monkeypatch.setattr("core.model_client.urllib.request.urlopen", request)
    client.chat([{"role": "user", "content": "work"}])
    assert load_api_usage_totals(path)["total_tokens"] == 40
    assert load_api_usage_totals(path)["in_flight_reserved_tokens"] == 0
    assert len(json.loads(path.read_text())["sessions"]) == 1
    assert "never-save" not in path.read_text()
    resumed = OpenAICompatibleClient(config, initial_usage=load_api_usage_totals(path))
    assert resumed.budget_snapshot()["total_tokens"] == 40


def test_over_limit_settlement_is_still_checkpointed(monkeypatch, tmp_path):
    path = tmp_path / "api_usage.json"
    config = ModelConfig("https://example.test/v1", "unused", "fake", max_tokens=32, global_token_limit=200)
    client = OpenAICompatibleClient(config)
    client.on_budget_update = lambda _: save_api_usage_evidence(path, "run", client, config, "running", checkpoint=True)
    monkeypatch.setattr("core.model_client.urllib.request.urlopen", lambda *_, **__: Response({"total_tokens": 250}))
    with pytest.raises(RuntimeError, match="provider usage exceeded"):
        client.chat([{"role": "user", "content": "work"}])
    assert load_api_usage_totals(path)["total_tokens"] == 250


def test_windows_python3_resolves_to_active_interpreter(tmp_path):
    result = ShellRunner(tmp_path).execute({"command": 'python3 -c "print(6 * 7)"'})
    assert result.success, result.error or result.output
    assert "42" in result.output
    assert sys.executable in result.metadata["executed_command"]


class SequenceClient:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)

    def chat(self, *_, **__):
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def tool_call(action="write", path="result.txt", content="result"):
    return {"content": "", "tool_calls": [{"id": "call", "function": {"name": "file_editor", "arguments": json.dumps({"action": action, "path": path, "content": content})}}]}


def test_api_error_preserves_existing_tool_evidence(tmp_path):
    client = SequenceClient([tool_call(), RuntimeError("HTTP 503")])
    agent = ToolCallingAgent("worker", client, ToolRegistry([FileEditor(tmp_path)]), "work")
    result = agent.run(SubTask("work", "worker", "write file"), {})
    assert result.status == "failed"
    assert result.artifacts == ["result.txt"]
    assert result.tool_records[0]["success"]
    assert "model_request_failed" in result.failures[0]


def test_successful_repeated_reads_do_not_trigger_failed_loop_guard(tmp_path):
    (tmp_path / "result.txt").write_text("data")
    client = SequenceClient([tool_call("read")] * 4 + [{"content": "verified"}])
    result = ToolCallingAgent("worker", client, ToolRegistry([FileEditor(tmp_path)]), "work").run(SubTask("work", "worker", "read"), {})
    assert result.status == "success"
    assert len(result.tool_records) == 4


def test_three_consecutive_identical_failures_stop_with_evidence(tmp_path):
    client = SequenceClient([tool_call("read")] * 3)
    result = ToolCallingAgent("worker", client, ToolRegistry([FileEditor(tmp_path)]), "work").run(SubTask("work", "worker", "read"), {})
    assert result.status == "failed"
    assert "repeated_tool_call" in result.failures
    assert len(result.tool_records) == 3


@pytest.mark.parametrize("message", [{"content": ""}, {"content": "partial", "_finish_reason": "length"}])
def test_empty_or_truncated_reply_cannot_pass_task(tmp_path, message):
    agent = ToolCallingAgent("worker", SequenceClient([message]), ToolRegistry([FileEditor(tmp_path)]), "work")
    assert agent.run(SubTask("work", "worker", "work"), {}).status == "failed"


class RecordingAgent(Agent):
    role = "worker"

    def __init__(self, workspace):
        self.workspace = workspace
        self.calls = Counter()
        self.interrupt = True

    def run(self, task, context):
        self.calls[task.id] += 1
        if task.id == "second" and self.interrupt:
            raise KeyboardInterrupt("simulated process interruption")
        name = task.id + ".txt"
        (self.workspace / name).write_text("produced " + task.id)
        return AgentResult(task.id, "success", summary="verified", artifacts=[name])


@pytest.mark.parametrize("mutate,expected_first", [(False, 1), (True, 2)])
def test_interrupted_phase_resumes_only_valid_successes(tmp_path, mutate, expected_first):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    agent = RecordingAgent(workspace)
    registry = AgentRegistry()
    registry.register(agent)
    plan = Plan("goal", [SubTask("first", "worker", "first"), SubTask("second", "worker", "second", depends_on=["first"])])
    store = LongHorizonStore(tmp_path / "runs")
    orchestrator = Orchestrator(registry)
    controller = LongHorizonController(orchestrator, lambda _: plan, store, workspace_path=str(workspace), local_recovery=LocalDAGRecoveryController(orchestrator))
    with pytest.raises(KeyboardInterrupt):
        controller.run("goal", run_id="resume")
    assert store.load("resume").pending_plan
    if mutate:
        (workspace / "first.txt").write_text("externally changed")
    agent.interrupt = False
    # A fresh controller models restarting the application, not just a function retry.
    resumed_orchestrator = Orchestrator(registry)
    resumed = LongHorizonController(resumed_orchestrator, lambda _: pytest.fail("must use pending plan"), LongHorizonStore(tmp_path / "runs"), workspace_path=str(workspace), local_recovery=LocalDAGRecoveryController(resumed_orchestrator)).run("goal", run_id="resume", resume=True)
    assert resumed.status == "completed"
    assert agent.calls["first"] == expected_first
    assert agent.calls["second"] == 2
    assert resumed.phase_reports[0].executed_task_count == expected_first


def test_old_phase_limit_can_be_expanded_and_finished(tmp_path):
    store = LongHorizonStore(tmp_path)
    state = LongHorizonState("old", "goal", 6, 100, status="budget_exhausted", phase=6, last_error="max_phases_exceeded")
    state.last_evaluation = GoalEvaluation(False, "continue").to_dict()
    store.save(state)
    registry = AgentRegistry()
    registry.register(DeterministicAgent("worker"))
    controller = LongHorizonController(Orchestrator(registry), lambda _: None, store, max_phases=12, replanner=lambda *_: Plan("goal", [SubTask("finish", "worker", "finish")]))
    result = controller.run("goal", run_id="old", resume=True)
    assert result.status == "completed"
    assert result.state.phase == 7
    assert result.state.max_phases == 12


def test_event_log_concurrent_writes_redaction_and_partial_tail_repair(tmp_path):
    store = LongHorizonStore(tmp_path)
    store.append_event("run", "first", {"api_key": "never-save", "text": "Bearer abcdef"})
    path = store.run_dir("run") / "events.jsonl"
    with path.open("a") as stream:
        stream.write('{"partial":')
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda index: store.append_event("run", "parallel", {"index": index}), range(40)))
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == 41
    assert "never-save" not in path.read_text()
    assert {r["payload"]["index"] for r in records[1:]} == set(range(40))


def test_api_failure_pauses_same_phase_then_recovers(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    class ApiAgent(Agent):
        role = "worker"
        calls = Counter()
        available = False
        def run(self, task, context):
            self.calls[task.id] += 1
            if task.id == "api" and not self.available:
                return AgentResult(task.id, "failed", failures=["model_request_failed: HTTP 503"])
            return AgentResult(task.id, "success", summary="verified")
    agent = ApiAgent()
    registry = AgentRegistry()
    registry.register(agent)
    plan = Plan("goal", [SubTask("prepare", "worker", "prepare"), SubTask("api", "worker", "api", depends_on=["prepare"])])
    orchestrator = Orchestrator(registry)
    store = LongHorizonStore(tmp_path / "runs")
    controller = LongHorizonController(orchestrator, lambda _: plan, store, workspace_path=str(workspace), local_recovery=LocalDAGRecoveryController(orchestrator))
    paused = controller.run("goal", run_id="api-resume")
    assert paused.status == "paused"
    assert paused.state.phase == 0 and paused.state.pending_plan
    assert agent.calls == Counter(prepare=1, api=1)
    agent.available = True
    result = controller.run("goal", run_id="api-resume", resume=True)
    assert result.status == "completed" and result.state.phase == 1
    assert agent.calls == Counter(prepare=1, api=2)


def test_local_repair_keeps_frozen_context_and_prior_evidence():
    class RepairAgent(Agent):
        role = "worker"
        def run(self, task, context):
            if task.id == "prepare":
                return AgentResult(task.id, "success", summary="needed input")
            if not task.metadata.get("local_recovery_feedback"):
                return AgentResult(task.id, "failed", tool_records=[{"tool": "first_attempt", "success": True}], failures=["repair required"])
            assert context["prepare"].summary == "needed input"
            assert task.metadata["local_recovery_feedback"]["prior_tool_results"][0]["tool"] == "first_attempt"
            return AgentResult(task.id, "success", summary="repaired", tool_records=[{"tool": "repair", "success": True}])
    registry = AgentRegistry()
    registry.register(RepairAgent())
    plan = Plan("goal", [SubTask("prepare", "worker", "prepare", max_retries=0), SubTask("repair", "worker", "repair", depends_on=["prepare"], max_retries=0)])
    outcome = LocalDAGRecoveryController(Orchestrator(registry)).run(plan, 10)
    assert outcome.report.status == "success"
    assert [r["tool"] for r in outcome.report.results["repair"].tool_records] == ["first_attempt", "repair"]


def test_unconfirmed_tokens_survive_restart_without_becoming_provider_usage():
    config = ModelConfig("https://example.test/v1", "unused", "fake", global_token_limit=100)
    budget = ModelCallBudget(config, {"total_tokens": 20, "requests": 1, "in_flight_reserved_tokens": 70})
    snapshot = budget.snapshot()
    assert snapshot["total_tokens"] == 20
    assert snapshot["unconfirmed_reserved_tokens"] == 70
    assert snapshot["remaining_tokens"] == 10
    with pytest.raises(RuntimeError, match="global token budget exhausted"):
        budget.reserve(15)


def test_actual_transport_retries_obey_model_call_cap(monkeypatch):
    config = ModelConfig("https://example.test/v1", "unused", "fake", max_model_calls=2)
    requests = []
    def request(*_, **__):
        requests.append(1)
        raise urllib.error.HTTPError(config.base_url, 503, "busy", {"Retry-After": "0"}, io.BytesIO(b"busy"))
    monkeypatch.setattr("core.model_client.urllib.request.urlopen", request)
    client = OpenAICompatibleClient(config)
    with pytest.raises(RuntimeError, match="model call budget"):
        client.chat([{"role": "user", "content": "work"}])
    assert len(requests) == 2
    assert client.budget_snapshot()["in_flight_reserved_tokens"] == 0


def test_ui_accepts_long_task_limits_without_network():
    class Value:
        def __init__(self, value): self.value = value
        def get(self): return self.value
    values = {"mode": "API 模型", "api_key": "unused", "model_name": "fake", "api_timeout": "120", "replan_attempts": "2", "max_tokens": "4096", "global_token_limit": "10000000", "max_model_calls": "1500", "max_runtime_seconds": "21600", "max_phases": "30", "max_total_tasks": "500", "base_url": "https://example.test/v1", "temperature": "0.2"}
    config = FreshUI._config(SimpleNamespace(**{key: Value(value) for key, value in values.items()}))
    assert config.long_horizon_max_phases == 30
    assert config.long_horizon_max_tasks == 500
    assert config.max_model_calls == 1500
    assert config.max_runtime_seconds == 21600


def test_checkpoint_failure_blocks_transport_and_releases_reservation(monkeypatch):
    client = OpenAICompatibleClient(ModelConfig("https://example.test/v1", "unused", "fake"))
    def failed_checkpoint(_):
        raise OSError("disk unavailable")
    client.on_budget_update = failed_checkpoint
    monkeypatch.setattr("core.model_client.urllib.request.urlopen", lambda *_, **__: pytest.fail("must not send without durable budget checkpoint"))
    with pytest.raises(RuntimeError, match="checkpoint failed"):
        client.chat([{"role": "user", "content": "work"}])
    assert client.budget_snapshot()["in_flight_reserved_tokens"] == 0


def test_cached_verification_is_rerun_and_dependency_changes_invalidate_downstream(tmp_path):
    store = LongHorizonStore(tmp_path / "runs")
    tasks = [SubTask("first", "worker", "produce"), SubTask("verify", "worker", "verify", depends_on=["first"], metadata={"checks": [{"id": "check", "check_type": "command", "command": "python -m unittest"}]})]
    plan = Plan("goal", tasks)
    for task in tasks:
        result = AgentResult(task.id, "success", summary="verified", tool_records=[{"tool": "shell_runner", "arguments": {"command": "python -m unittest"}, "success": True, "exit_code": 0}])
        store.append_event("run", "task_finished", {"phase": 1, "task_id": task.id, "result": asdict(result), "task_fingerprint": store.task_fingerprint(task), "artifact_hashes": {}})
    assert set(store.successful_results("run", 1, plan, tmp_path)) == {"first"}
    store.append_event("run", "task_started", {"phase": 1, "task_id": "first"})
    assert store.successful_results("run", 1, plan, tmp_path) == {}
