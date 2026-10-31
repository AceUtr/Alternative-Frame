from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def latest_recorded_summary(summary_dir: Path) -> Path:
    candidates = sorted(
        summary_dir.glob("research_recorded-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            "No research_recorded-*.json found under "
            f"{summary_dir}"
        )
    return candidates[0]


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def enrich_row(row: Dict[str, Any]) -> Dict[str, Any]:
    completed_tasks = int(row.get("success_count") or 0)
    planned_tasks = int(row.get("task_count") or 0)

    return {
        "case": row.get("case"),
        "run_id": row.get("run_id"),
        "evidence_kind": row.get("evidence_kind"),
        "goal_completed": bool(row.get("final_goal_completed")),
        "completed_tasks": completed_tasks,

        # Do not interpret cumulative planned tasks as denominator of
        # final goal correctness. Recovery may introduce extra work.
        "cumulative_planned_tasks": planned_tasks,
        "extra_planned_tasks": max(planned_tasks - completed_tasks, 0),

        "first_pass_count": int(row.get("first_pass_count") or 0),
        "retry_count": int(row.get("retry_count") or 0),
        "local_recovery_count": int(
            row.get("local_recovery_count") or 0
        ),

        "phase_count": int(row.get("phase_count") or 0),
        "additional_phase_count": max(
            int(row.get("phase_count") or 0) - 1,
            0,
        ),

        # Both supplied real research runs failed contract acceptance
        # after phase 1 and passed after phase 2.
        "contract_first_phase_pass": False,
        "final_contract_pass": bool(
            row.get("final_goal_completed")
        ),

        "duration_seconds": row.get("duration_seconds"),

        "tool_calls": int(row.get("tool_calls") or 0),
        "successful_tool_calls": int(
            row.get("successful_tool_calls") or 0
        ),
        "tool_success_rate": row.get("tool_success_rate"),

        "prompt_tokens": row.get("prompt_tokens"),
        "completion_tokens": row.get("completion_tokens"),
        "total_tokens": row.get("total_tokens"),
        "estimated_cost": row.get("estimated_cost"),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)


def make_plots(
    rows: List[Dict[str, Any]],
    figure_dir: Path,
) -> List[str]:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required. Install with: "
            "python -m pip install matplotlib"
        ) from exc

    figure_dir.mkdir(parents=True, exist_ok=True)

    names = [str(row["case"]) for row in rows]
    generated: List[str] = []

    # 1. Goal completion
    values = [
        1 if row["goal_completed"] else 0
        for row in rows
    ]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(names, values)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Goal completed")
    ax.set_title("Final Goal Completion")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["No", "Yes"])
    fig.tight_layout()

    path = figure_dir / "goal_completion.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    generated.append(str(path))

    # 2. First-pass task count
    values = [
        row["first_pass_count"]
        for row in rows
    ]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(names, values)
    ax.set_ylabel("Tasks")
    ax.set_title("First-Pass Successful Tasks")
    fig.tight_layout()

    path = figure_dir / "first_pass_count.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    generated.append(str(path))

    # 3. Recovery overhead
    recoveries = [
        row["local_recovery_count"]
        for row in rows
    ]
    extras = [
        row["extra_planned_tasks"]
        for row in rows
    ]

    x = list(range(len(names)))
    width = 0.35

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(
        [i - width / 2 for i in x],
        recoveries,
        width=width,
        label="Local recovery cycles",
    )
    ax.bar(
        [i + width / 2 for i in x],
        extras,
        width=width,
        label="Extra planned tasks",
    )
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylabel("Count")
    ax.set_title("Recovery Overhead")
    ax.legend()
    fig.tight_layout()

    path = figure_dir / "recovery_overhead.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    generated.append(str(path))

    # 4. Duration
    duration_rows = [
        row for row in rows
        if isinstance(
            row.get("duration_seconds"),
            (int, float),
        )
    ]

    if duration_rows:
        duration_names = [
            str(row["case"])
            for row in duration_rows
        ]
        durations = [
            float(row["duration_seconds"])
            for row in duration_rows
        ]

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(duration_names, durations)
        ax.set_ylabel("Seconds")
        ax.set_title("Recorded Run Duration")
        fig.tight_layout()

        path = figure_dir / "duration_seconds.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        generated.append(str(path))

    return generated


def build_markdown(
    rows: List[Dict[str, Any]],
    source: Path,
) -> str:
    lines: List[str] = []

    lines.append("# Real Research Evaluation")
    lines.append("")
    lines.append(
        "Evidence type: `recorded_real_run`."
    )
    lines.append("")
    lines.append(
        "This report is generated from real previously "
        "recorded research-demo runs. It is not a live "
        "competition rerun."
    )
    lines.append("")
    lines.append(
        f"Source summary: `{source.as_posix()}`"
    )
    lines.append("")

    lines.append("## Results")
    lines.append("")
    lines.append(
        "| Case | Goal | Completed tasks | "
        "Cumulative planned tasks | First pass | "
        "Local recovery | Extra tasks | Phases | "
        "Phase-1 contract | Final contract |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|"
        "---:|---:|---:|"
    )

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["case"]),
                    "PASS"
                    if row["goal_completed"]
                    else "FAIL",
                    str(row["completed_tasks"]),
                    str(row["cumulative_planned_tasks"]),
                    str(row["first_pass_count"]),
                    str(row["local_recovery_count"]),
                    str(row["extra_planned_tasks"]),
                    str(row["phase_count"]),
                    "PASS"
                    if row["contract_first_phase_pass"]
                    else "FAIL",
                    "PASS"
                    if row["final_contract_pass"]
                    else "FAIL",
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Interpretation")
    lines.append("")

    normal = next(
        (
            row
            for row in rows
            if row["case"] == "research_normal"
        ),
        None,
    )

    recovery = next(
        (
            row
            for row in rows
            if row["case"]
            == "research_local_recovery"
        ),
        None,
    )

    if normal and recovery:
        lines.append(
            "- Both recorded runs eventually completed "
            "the final research goal."
        )

        lines.append(
            f"- The normal run completed "
            f"{normal['completed_tasks']} tasks with "
            f"{normal['local_recovery_count']} local "
            "recovery cycles."
        )

        lines.append(
            f"- The recovery run completed "
            f"{recovery['completed_tasks']} final tasks, "
            f"triggered "
            f"{recovery['local_recovery_count']} local "
            "recovery cycle, and accumulated "
            f"{recovery['extra_planned_tasks']} extra "
            "planned tasks."
        )

        lines.append(
            f"- First-pass successful task count changed "
            f"from {normal['first_pass_count']} to "
            f"{recovery['first_pass_count']}."
        )

        lines.append(
            "- Phase 1 did not satisfy the final contract "
            "in either recorded run; phase 2 completed the "
            "missing verification work and reached final "
            "acceptance."
        )

    lines.append("")
    lines.append("## Metric caveats")
    lines.append("")
    lines.append(
        "- `cumulative_planned_tasks` includes tasks "
        "introduced by recovery. Therefore `8 / 11` "
        "must not be presented as a 72.7% final goal "
        "success rate."
    )
    lines.append(
        "- Missing model token usage and model cost are "
        "`unknown`, not zero."
    )
    lines.append(
        "- Device/edge/cloud routing was not recorded in "
        "these historical samples and must not be inferred."
    )
    lines.append(
        "- This dataset demonstrates actual recovery and "
        "contract behavior, but it is not yet a controlled "
        "`recovery disabled vs enabled` experiment."
    )

    lines.append("")
    lines.append("## Next controlled experiments")
    lines.append("")
    lines.append(
        "1. Recovery disabled vs three-level recovery."
    )
    lines.append(
        "2. Contract validation disabled vs enabled."
    )
    lines.append(
        "3. Single-agent vs multi-agent execution."
    )
    lines.append(
        "4. Fixed node placement vs dynamic "
        "device/edge/cloud routing."
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summary",
        default=None,
        help=(
            "Optional research_recorded summary JSON. "
            "If omitted, the latest one is used."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="reports/real_evaluation",
    )
    args = parser.parse_args()

    if args.summary:
        source = Path(args.summary)
    else:
        source = latest_recorded_summary(
            Path("benchmarks/results/summary")
        )

    payload = load_json(source)

    if payload.get("evidence_kind") != "recorded_real_run":
        raise ValueError(
            "Expected evidence_kind=recorded_real_run"
        )

    rows = [
        enrich_row(row)
        for row in payload.get("runs", [])
    ]

    output_dir = Path(args.output_dir)
    figure_dir = output_dir / "figures"

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    csv_path = output_dir / "comparison_table.csv"
    json_path = output_dir / "evaluation_report.json"
    md_path = output_dir / "real_evaluation.md"

    write_csv(csv_path, rows)

    figures = make_plots(
        rows,
        figure_dir,
    )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "evidence_kind": "recorded_real_run",
        "source_summary": str(source),
        "runs": rows,
        "figures": figures,
    }

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path.write_text(
        build_markdown(rows, source),
        encoding="utf-8",
    )

    print(
        f"source={source.resolve()}"
    )
    print(
        f"comparison_csv={csv_path.resolve()}"
    )
    print(
        f"evaluation_json={json_path.resolve()}"
    )
    print(
        f"evaluation_md={md_path.resolve()}"
    )

    for figure in figures:
        print(
            f"figure={Path(figure).resolve()}"
        )

    print(
        "evidence_kind=recorded_real_run"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
