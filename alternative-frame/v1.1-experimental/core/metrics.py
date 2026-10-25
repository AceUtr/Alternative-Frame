from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict


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
    model_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    human_interventions: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class MetricsRecorder:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, metrics: RunMetrics) -> None:
        line = json.dumps(asdict(metrics), ensure_ascii=False) + "\n"
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
        except PermissionError:
            # Some managed workspaces make copied subdirectories read-only at
            # runtime. Keep the run measurable rather than silently dropping it.
            fallback = Path(r"C:\tmp\alternative-frame-v0.1-results.jsonl")
            try:
                with fallback.open("a", encoding="utf-8") as f:
                    f.write(line)
                print(f"warning: project results path is not writable; wrote metrics to {fallback}")
            except PermissionError:
                print("warning: metrics paths are not writable in this managed session; metric_json=" + line.rstrip())


def metrics_from_report(report, domain: str, mode: str, model: str, started: float, run_id: str, metadata=None) -> RunMetrics:
    values = list(report.results.values())
    return RunMetrics(
        run_id=run_id,
        domain=domain,
        mode=mode,
        model=model,
        status=report.status,
        rounds=report.rounds,
        task_count=len(values),
        success_count=sum(r.status == "success" for r in values),
        failed_count=sum(r.status != "success" for r in values),
        retry_count=sum(max(0, r.attempts - 1) for r in values),
        duration_seconds=round(time.perf_counter() - started, 3),
        model_calls=sum(1 for r in values if any(e == "api_response_received" for e in r.evidence)),
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        metadata=metadata or {},
    )
