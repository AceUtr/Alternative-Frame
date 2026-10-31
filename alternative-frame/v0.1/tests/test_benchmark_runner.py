import json
from pathlib import Path

from core.metrics import load_metrics, summarize_metrics
from run_benchmarks import BenchmarkCase, BenchmarkConfig, prepare_workspace, run_benchmark


def test_prepare_workspace_isolates_fixture(tmp_path: Path):
    fixture = tmp_path / "fixture"
    fixture.mkdir(); (fixture / "marker.txt").write_text("clean", encoding="utf-8")
    case = BenchmarkCase(name="x", domain="research", task="research_plan", fixture=str(fixture))
    first = prepare_workspace(tmp_path / "workspaces", case, "run-1")
    (first / "marker.txt").write_text("dirty", encoding="utf-8")
    second = prepare_workspace(tmp_path / "workspaces", case, "run-2")
    assert (second / "marker.txt").read_text(encoding="utf-8") == "clean"
    assert first != second


def test_benchmark_outputs_recompute_from_raw(tmp_path: Path, monkeypatch):
    import run_benchmarks
    monkeypatch.setattr(run_benchmarks, "ROOT", tmp_path)
    config = BenchmarkConfig(
        benchmark_name="test",
        output_root="results",
        workspace_root="workspaces",
        cases=[BenchmarkCase(name="research", domain="research", task="research_plan", repeats=2)],
    )
    outputs = run_benchmark(config)
    rows = load_metrics(outputs["raw"])
    assert len(rows) == 2
    persisted = json.loads(outputs["summary_json"].read_text(encoding="utf-8"))["cases"][0]
    recomputed = summarize_metrics(rows)
    assert persisted["run_count"] == recomputed.run_count
    assert persisted["subtask_success_rate"] == recomputed.subtask_success_rate
    assert persisted["final_goal_completion_rate"] == recomputed.final_goal_completion_rate


def test_runner_failure_does_not_stop_later_samples(tmp_path: Path, monkeypatch):
    import run_benchmarks
    monkeypatch.setattr(run_benchmarks, "ROOT", tmp_path)
    original = run_benchmarks.execute_case
    calls = {"n": 0}
    def flaky(case, workspace, run_id, repeat_index):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("synthetic failure")
        return original(case, workspace, run_id, repeat_index)
    monkeypatch.setattr(run_benchmarks, "execute_case", flaky)
    config = BenchmarkConfig(
        benchmark_name="failure-continue",
        output_root="results",
        workspace_root="workspaces",
        cases=[BenchmarkCase(name="research", domain="research", task="research_plan", repeats=2)],
    )
    outputs = run_benchmark(config)
    rows = load_metrics(outputs["raw"])
    assert len(rows) == 2
    assert rows[0].status == "runner_failed"
    assert rows[1].status == "success"
    assert "synthetic failure" in rows[0].metadata["failure_reason"]
