from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
from uuid import uuid4

from core.agents import AgentRegistry, DeterministicAgent
from core.metrics import MetricsRecorder, RunMetrics, summarize_metrics, metrics_from_report
from core.orchestrator import Orchestrator
from domains.presets import research_plan, software_plan

ROOT = Path(__file__).resolve().parent


@dataclass
class BenchmarkCase:
    name: str
    domain: str
    task: str
    mode: str = "multi_agent"
    repeats: int = 1
    model: str = "deterministic"
    seed: int = 0
    max_workers: int = 4
    budget: Dict[str, Any] = field(default_factory=dict)
    fixture: str | None = None
    pricing: Dict[str, Any] | None = None


@dataclass
class BenchmarkConfig:
    benchmark_name: str
    cases: List[BenchmarkCase]
    output_root: str = "benchmarks/results"
    workspace_root: str = "benchmarks/workspaces"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BenchmarkConfig":
        cases = [BenchmarkCase(**item) for item in data.get("cases", [])]
        if not cases:
            raise ValueError("benchmark config must contain at least one case")
        for case in cases:
            if case.repeats < 1:
                raise ValueError(f"case {case.name}: repeats must be positive")
            if case.mode not in {"single_agent", "multi_agent"}:
                raise ValueError(f"case {case.name}: unsupported mode {case.mode}")
        return cls(
            benchmark_name=data.get("benchmark_name", "benchmark"),
            cases=cases,
            output_root=data.get("output_root", "benchmarks/results"),
            workspace_root=data.get("workspace_root", "benchmarks/workspaces"),
        )


def load_config(path: str | Path) -> BenchmarkConfig:
    source = Path(path)
    return BenchmarkConfig.from_dict(json.loads(source.read_text(encoding="utf-8")))


def _registry() -> AgentRegistry:
    registry = AgentRegistry()
    for role in ["researcher", "experimenter", "reviewer", "analyst", "architect", "developer", "tester"]:
        registry.register(DeterministicAgent(role))
    return registry


def _plan_for(case: BenchmarkCase):
    key = case.task.strip().lower()
    if key in {"research", "research_plan", "research_demo"}:
        return research_plan()
    if key in {"software", "software_plan", "software_demo", "software_engineering"}:
        return software_plan()
    raise ValueError(f"unknown built-in task: {case.task}")


def prepare_workspace(workspace_root: Path, case: BenchmarkCase, run_id: str) -> Path:
    workspace = workspace_root / case.name / run_id
    if workspace.exists():
        raise FileExistsError(f"workspace already exists: {workspace}")
    workspace.mkdir(parents=True, exist_ok=False)
    if case.fixture:
        fixture = (ROOT / case.fixture).resolve() if not Path(case.fixture).is_absolute() else Path(case.fixture).resolve()
        if not fixture.exists():
            raise FileNotFoundError(f"fixture not found: {fixture}")
        if fixture.is_dir():
            for child in fixture.iterdir():
                target = workspace / child.name
                if child.is_dir(): shutil.copytree(child, target)
                else: shutil.copy2(child, target)
        else:
            shutil.copy2(fixture, workspace / fixture.name)
    return workspace


def execute_case(case: BenchmarkCase, workspace: Path, run_id: str, repeat_index: int) -> RunMetrics:
    random.seed(case.seed + repeat_index)
    plan = _plan_for(case)
    started = time.perf_counter()
    # Current smoke implementation uses the same role registry for both modes;
    # the experimental factor is serial vs dependency-aware parallel execution.
    # This is intentionally labeled as a pipeline/stub comparison, not final competition evidence.
    parallel = case.mode == "multi_agent"
    report = Orchestrator(_registry(), max_workers=max(1, case.max_workers)).run(plan, parallel=parallel)
    return metrics_from_report(
        report,
        domain=case.domain,
        mode=case.mode,
        model=case.model,
        started=started,
        run_id=run_id,
        plan=plan,
        pricing=case.pricing,
        metadata={
            "benchmark_case": case.name,
            "repeat_index": repeat_index,
            "seed": case.seed + repeat_index,
            "budget": case.budget,
            "workspace": str(workspace),
            "evidence_kind": "stub_pipeline_validation",
        },
    )


def _summary_row(case_name: str, runs: Iterable[RunMetrics]) -> Dict[str, Any]:
    rows = list(runs)
    summary = summarize_metrics(rows)
    data = asdict(summary)
    data["case_name"] = case_name
    data["run_ids"] = [row.run_id for row in rows]
    return data


def _write_summary_csv(path: Path, summaries: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flat_rows = []
    for row in summaries:
        flat = dict(row)
        for key in ["node_distribution", "node_failures", "node_durations"]:
            nested = flat.pop(key, {}) or {}
            for nested_key, value in nested.items():
                flat[f"{key}.{nested_key}"] = value
        flat["run_ids"] = ";".join(flat.get("run_ids", []))
        flat_rows.append(flat)
    keys = sorted({key for row in flat_rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader(); writer.writerows(flat_rows)


def run_benchmark(config: BenchmarkConfig) -> Dict[str, Path]:
    output_root = (ROOT / config.output_root).resolve()
    workspace_root = (ROOT / config.workspace_root).resolve()
    raw_dir = output_root / "raw"; summary_dir = output_root / "summary"
    raw_dir.mkdir(parents=True, exist_ok=True); summary_dir.mkdir(parents=True, exist_ok=True); workspace_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    raw_path = raw_dir / f"{config.benchmark_name}-{stamp}.jsonl"
    recorder = MetricsRecorder(raw_path)
    grouped: Dict[str, List[RunMetrics]] = {case.name: [] for case in config.cases}

    for case in config.cases:
        for repeat_index in range(case.repeats):
            run_id = f"{case.name}-{stamp}-{repeat_index+1}-{uuid4().hex[:6]}".replace(" ", "_")
            workspace = prepare_workspace(workspace_root, case, run_id)
            try:
                metrics = execute_case(case, workspace, run_id, repeat_index)
            except Exception as exc:
                metrics = RunMetrics(
                    run_id=run_id, domain=case.domain, mode=case.mode, model=case.model,
                    status="runner_failed", rounds=0, task_count=0, success_count=0,
                    failed_count=0, retry_count=0, duration_seconds=0.0,
                    final_goal_completed=False,
                    metadata={
                        "benchmark_case": case.name, "repeat_index": repeat_index,
                        "workspace": str(workspace), "failure_reason": f"{type(exc).__name__}: {exc}",
                        "evidence_kind": "stub_pipeline_validation",
                    },
                )
            recorder.append(metrics)
            grouped[case.name].append(metrics)

    summaries = [_summary_row(name, runs) for name, runs in grouped.items()]
    summary_json = summary_dir / f"{config.benchmark_name}-{stamp}.json"
    summary_csv = summary_dir / f"{config.benchmark_name}-{stamp}.csv"
    summary_json.write_text(json.dumps({"benchmark_name": config.benchmark_name, "cases": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary_csv(summary_csv, summaries)
    return {"raw": raw_path, "summary_json": summary_json, "summary_csv": summary_csv}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated, append-only Alternative-Frame benchmarks")
    parser.add_argument("--config", required=True, help="Path to benchmark JSON config")
    args = parser.parse_args()
    config = load_config(args.config)
    outputs = run_benchmark(config)
    for key, path in outputs.items(): print(f"{key}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
