import json
from pathlib import Path
from types import SimpleNamespace

from core.metrics import (
    MetricsRecorder,
    RunMetrics,
    load_metrics,
    metrics_from_report,
    sanitize_sensitive,
    summarize_metrics,
)
from core.models import AgentResult


def make_run(**overrides):
    values = dict(
        run_id="run-1",
        domain="software",
        mode="stub",
        model="deterministic",
        status="success",
        rounds=1,
        task_count=2,
        success_count=1,
        failed_count=1,
        retry_count=1,
        duration_seconds=4.0,
        final_goal_completed=True,
        first_pass_count=1,
        tool_calls=2,
        successful_tool_calls=1,
        unknown_node_task_count=2,
    )
    values.update(overrides)
    return RunMetrics(**values)


def test_empty_summary_uses_unknown_rates():
    summary = summarize_metrics([])
    assert summary.run_count == 0
    assert summary.final_goal_completion_rate is None
    assert summary.subtask_success_rate is None
    assert summary.mean_duration_seconds is None


def test_summary_formulas():
    summary = summarize_metrics([
        make_run(run_id="a", task_count=2, success_count=2, first_pass_count=1, retry_count=1),
        make_run(run_id="b", final_goal_completed=False, task_count=2, success_count=1, first_pass_count=1, retry_count=2),
    ])
    assert summary.final_goal_completion_rate == 0.5
    assert summary.subtask_success_rate == 0.75
    assert summary.first_pass_rate == 0.5
    assert summary.retry_count == 3
    assert summary.tool_success_rate == 0.5


def test_unknown_tokens_remain_unknown_in_summary():
    summary = summarize_metrics([
        make_run(total_tokens=120),
        make_run(run_id="b", total_tokens=None),
    ])
    assert summary.total_tokens is None


def test_metrics_from_report_calculates_retries_and_tools():
    report = SimpleNamespace(
        status="success",
        rounds=2,
        local_recovery_cycles=1,
        results={
            "t1": AgentResult(
                "t1",
                "success",
                attempts=2,
                evidence=["api_response_received"],
                tool_records=[
                    {"tool": "test_runner", "success": True, "metadata": {"usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}}
                ],
            ),
            "t2": AgentResult("t2", "failed", attempts=1),
        },
    )
    metrics = metrics_from_report(report, "software", "real", "model-x", 0.0, "run-x")
    assert metrics.task_count == 2
    assert metrics.success_count == 1
    assert metrics.retry_count == 1
    assert metrics.first_pass_count == 0
    assert metrics.local_recovery_count == 1
    assert metrics.tool_calls == 1
    assert metrics.successful_tool_calls == 1
    assert metrics.total_tokens == 8


def test_missing_usage_is_unknown_not_zero():
    report = SimpleNamespace(
        status="success",
        rounds=1,
        local_recovery_cycles=0,
        results={"t1": AgentResult("t1", "success", evidence=["api_response_received"])},
    )
    metrics = metrics_from_report(report, "research", "real", "model-x", 0.0, "run-x")
    assert metrics.model_calls == 1
    assert metrics.total_tokens is None


def test_sensitive_fields_are_redacted():
    cleaned = sanitize_sensitive({
        "api_key": "secret-value",
        "headers": {"Authorization": "Bearer abc"},
        "safe": "ok",
    })
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["headers"]["Authorization"] == "[REDACTED]"
    assert cleaned["safe"] == "ok"


def test_jsonl_append_and_corrupt_line_tolerance(tmp_path: Path):
    path = tmp_path / "results.jsonl"
    recorder = MetricsRecorder(path)
    recorder.append(make_run(metadata={"password": "do-not-save"}))
    with path.open("a", encoding="utf-8") as stream:
        stream.write("{broken json\n")
        stream.write(json.dumps(make_run(run_id="run-2").to_dict(), ensure_ascii=False) + "\n")

    rows = load_metrics(path)
    assert [row.run_id for row in rows] == ["run-1", "run-2"]
    persisted = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert persisted["metadata"]["password"] == "[REDACTED]"


def test_legacy_jsonl_is_readable(tmp_path: Path):
    path = tmp_path / "legacy.jsonl"
    legacy = {
        "run_id": "legacy-1",
        "domain": "research",
        "mode": "stub",
        "model": "deterministic",
        "status": "success",
        "rounds": 1,
        "task_count": 1,
        "success_count": 1,
        "failed_count": 0,
        "retry_count": 0,
        "duration_seconds": 0.1,
        "model_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "human_interventions": 0,
        "metadata": {},
    }
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    rows = load_metrics(path)
    assert len(rows) == 1
    assert rows[0].schema_version == "0.1"
    assert rows[0].metadata["legacy_token_zero_may_mean_unknown"] is True
