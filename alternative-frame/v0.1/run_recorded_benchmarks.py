from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from core.recorded_metrics import metrics_from_recorded_run


def load_config(path: str | Path) -> Dict[str, Any]:
    return json.loads(
        Path(path).read_text(encoding="utf-8-sig")
    )


def safe_rate(numerator: int, denominator: int):
    if denominator <= 0:
        return None
    return numerator / denominator


def summary_row(case_name: str, metric) -> Dict[str, Any]:
    return {
        "case": case_name,
        "run_id": metric.run_id,
        "evidence_kind": metric.metadata.get("evidence_kind"),
        "status": metric.status,
        "final_goal_completed": metric.final_goal_completed,
        "task_count": metric.task_count,
        "success_count": metric.success_count,
        "failed_count": metric.failed_count,
        "task_success_rate": safe_rate(
            metric.success_count,
            metric.task_count,
        ),
        "first_pass_count": metric.first_pass_count,
        "first_pass_rate": safe_rate(
            metric.first_pass_count,
            metric.success_count,
        ),
        "retry_count": metric.retry_count,
        "local_recovery_count": metric.local_recovery_count,
        "phase_count": metric.phase_count,
        "duration_seconds": metric.duration_seconds,
        "tool_calls": metric.tool_calls,
        "successful_tool_calls": metric.successful_tool_calls,
        "tool_success_rate": safe_rate(
            metric.successful_tool_calls,
            metric.tool_calls,
        ),
        "prompt_tokens": metric.prompt_tokens,
        "completion_tokens": metric.completion_tokens,
        "total_tokens": metric.total_tokens,
        "estimated_cost": metric.estimated_cost,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="benchmarks/configs/research_recorded.json",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    raw_dir = Path("benchmarks/results/raw")
    summary_dir = Path("benchmarks/results/summary")

    raw_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    config_name = str(config.get("name") or "recorded")

    raw_path = raw_dir / f"{config_name}-{stamp}.jsonl"
    summary_json_path = (
        summary_dir / f"{config_name}-{stamp}.json"
    )
    summary_csv_path = (
        summary_dir / f"{config_name}-{stamp}.csv"
    )

    rows: List[Dict[str, Any]] = []

    with raw_path.open("a", encoding="utf-8") as raw_file:
        for case in config.get("cases", []):
            metric = metrics_from_recorded_run(
                case["run_dir"],
                domain=case.get("domain", "research"),
                mode=case.get("mode", "recorded_real_run"),
                model="unknown",
            )

            raw_record = asdict(metric)
            raw_record["benchmark_case"] = case["name"]
            raw_record["evidence_kind"] = "recorded_real_run"

            raw_file.write(
                json.dumps(
                    raw_record,
                    ensure_ascii=False,
                )
                + "\n"
            )

            rows.append(
                summary_row(case["name"], metric)
            )

    summary = {
        "benchmark": config_name,
        "evidence_kind": "recorded_real_run",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "case_count": len(rows),
        "runs": rows,
    }

    summary_json_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if rows:
        with summary_csv_path.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=list(rows[0].keys()),
            )
            writer.writeheader()
            writer.writerows(rows)

    print(f"raw={raw_path.resolve()}")
    print(f"summary_json={summary_json_path.resolve()}")
    print(f"summary_csv={summary_csv_path.resolve()}")
    print("evidence_kind=recorded_real_run")

    for row in rows:
        print(
            f"{row['case']}: "
            f"completed={row['final_goal_completed']} "
            f"tasks={row['success_count']}/{row['task_count']} "
            f"first_pass={row['first_pass_count']} "
            f"recovery={row['local_recovery_count']} "
            f"phases={row['phase_count']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
