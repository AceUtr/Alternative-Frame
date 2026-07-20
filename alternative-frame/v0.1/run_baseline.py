"""Run reproducible v0.1 orchestration baselines and record JSONL metrics."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from core.agents import AgentRegistry, DeterministicAgent
from core.metrics import MetricsRecorder, metrics_from_report
from core.orchestrator import Orchestrator
from domains.presets import research_plan, software_plan


ROOT = Path(__file__).parent


def registry() -> AgentRegistry:
    r = AgentRegistry()
    for role in ["researcher", "experimenter", "reviewer", "analyst", "architect", "developer", "tester"]:
        r.register(DeterministicAgent(role))
    return r


def run_one(domain, plan_factory, recorder):
    started = time.perf_counter()
    report = Orchestrator(registry(), max_workers=4).run(plan_factory())
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{domain}"
    metrics = metrics_from_report(report, domain, "stub", "deterministic", started, run_id, {
        "baseline_kind": "orchestration_only",
        "note": "No real file edits, experiments, tests, or LLM calls in v0.1 stub baseline.",
    })
    recorder.append(metrics)
    print(f"{domain}: status={metrics.status} tasks={metrics.task_count} rounds={metrics.rounds} duration={metrics.duration_seconds}s")


if __name__ == "__main__":
    recorder = MetricsRecorder(ROOT / "runs" / "results.jsonl")
    run_one("research", research_plan, recorder)
    run_one("software_engineering", software_plan, recorder)
    print(f"metrics_file={ROOT / 'runs' / 'results.jsonl'}")

