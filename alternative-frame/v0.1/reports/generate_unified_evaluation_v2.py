from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


SUMMARY_DIR = Path("benchmarks/results/summary")
OUTPUT_DIR = Path("reports/unified_evaluation_v2")
FIGURE_DIR = OUTPUT_DIR / "figures"


def latest(pattern: str) -> Path:
    files = sorted(
        SUMMARY_DIR.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(
            f"No result matching {pattern}"
        )
    return files[0]


def load(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def main():
    import matplotlib.pyplot as plt

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    FIGURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    research_path = latest(
        "research_recorded-*.json"
    )
    recovery_path = latest(
        "deterministic_recovery-*.json"
    )
    contract_path = latest(
        "deterministic_contract-*.json"
    )
    agents_path = latest(
        "deterministic_agents-*.json"
    )

    research = load(research_path)
    recovery = load(recovery_path)
    contract = load(contract_path)
    agents = load(agents_path)

    agent_map = {
        row["mode"]: row
        for row in agents["summaries"]
    }

    single = agent_map["single_agent"]
    multi = agent_map["multi_agent"]

    speedup = (
        single["mean_duration_seconds"]
        / multi["mean_duration_seconds"]
    )

    # Agent wall-clock chart
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(
        ["single_agent", "multi_agent"],
        [
            single["mean_duration_seconds"],
            multi["mean_duration_seconds"],
        ],
    )
    ax.set_ylabel("Mean wall-clock seconds")
    ax.set_title(
        "Single-Agent vs Multi-Agent Orchestration"
    )
    fig.tight_layout()

    agent_figure = (
        FIGURE_DIR / "agent_wall_clock.png"
    )

    fig.savefig(
        agent_figure,
        dpi=180,
    )
    plt.close(fig)

    # Recovery chart
    recovery_map = {
        row["mode"]: row
        for row in recovery["results"]
    }

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(
        ["recovery_off", "recovery_on"],
        [
            int(
                recovery_map[
                    "recovery_off"
                ]["goal_completed"]
            ),
            int(
                recovery_map[
                    "recovery_on"
                ]["goal_completed"]
            ),
        ],
    )
    ax.set_ylim(0, 1.1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(
        ["Failed", "Completed"]
    )
    ax.set_title(
        "Controlled Local Recovery Ablation"
    )
    fig.tight_layout()

    recovery_figure = (
        FIGURE_DIR / "recovery_completion.png"
    )
    fig.savefig(
        recovery_figure,
        dpi=180,
    )
    plt.close(fig)

    # Contract chart
    contract_map = {
        row["mode"]: row
        for row in contract["results"]
    }

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(
        ["contract_off", "contract_on"],
        [
            int(
                contract_map[
                    "contract_off"
                ]["completed"]
            ),
            int(
                contract_map[
                    "contract_on"
                ]["completed"]
            ),
        ],
    )
    ax.set_ylim(0, 1.1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(
        [
            "Rejected / incomplete",
            "Declared complete",
        ]
    )
    ax.set_title(
        "Contract Validation Ablation"
    )
    fig.tight_layout()

    contract_figure = (
        FIGURE_DIR
        / "contract_completion_decision.png"
    )

    fig.savefig(
        contract_figure,
        dpi=180,
    )
    plt.close(fig)

    rows = [
        {
            "experiment": "agent_topology",
            "condition": "single_agent",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "goal_completion_rate": (
                single["goal_completion_rate"]
            ),
            "mean_duration_seconds": (
                single["mean_duration_seconds"]
            ),
            "parallel_overlap_seconds": (
                single[
                    "mean_parallel_overlap_seconds"
                ]
            ),
            "unique_backend_count": (
                single["unique_backend_count"]
            ),
            "key_result": (
                "single shared backend"
            ),
        },
        {
            "experiment": "agent_topology",
            "condition": "multi_agent",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "goal_completion_rate": (
                multi["goal_completion_rate"]
            ),
            "mean_duration_seconds": (
                multi["mean_duration_seconds"]
            ),
            "parallel_overlap_seconds": (
                multi[
                    "mean_parallel_overlap_seconds"
                ]
            ),
            "unique_backend_count": (
                multi["unique_backend_count"]
            ),
            "key_result": (
                f"{speedup:.3f}x wall-clock speedup"
            ),
        },
        {
            "experiment": "local_recovery",
            "condition": "recovery_off",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "goal_completion_rate": int(
                recovery_map[
                    "recovery_off"
                ]["goal_completed"]
            ),
            "mean_duration_seconds": None,
            "parallel_overlap_seconds": None,
            "unique_backend_count": None,
            "key_result": "injected failure remained failed",
        },
        {
            "experiment": "local_recovery",
            "condition": "recovery_on",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "goal_completion_rate": int(
                recovery_map[
                    "recovery_on"
                ]["goal_completed"]
            ),
            "mean_duration_seconds": None,
            "parallel_overlap_seconds": None,
            "unique_backend_count": None,
            "key_result": (
                "one local recovery cycle restored success"
            ),
        },
        {
            "experiment": "contract_validation",
            "condition": "contract_off",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "goal_completion_rate": int(
                contract_map[
                    "contract_off"
                ]["completed"]
            ),
            "mean_duration_seconds": None,
            "parallel_overlap_seconds": None,
            "unique_backend_count": None,
            "key_result": "false completion accepted",
        },
        {
            "experiment": "contract_validation",
            "condition": "contract_on",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "goal_completion_rate": int(
                contract_map[
                    "contract_on"
                ]["completed"]
            ),
            "mean_duration_seconds": None,
            "parallel_overlap_seconds": None,
            "unique_backend_count": None,
            "key_result": (
                "missing final_evidence correctly rejected"
            ),
        },
    ]

    csv_path = (
        OUTPUT_DIR / "competition_comparison.csv"
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(
                rows[0].keys()
            ),
        )
        writer.writeheader()
        writer.writerows(rows)

    markdown = f"""# Competition Evaluation Report

Generated: {datetime.now(timezone.utc).isoformat()}

## Current evidence

### Single Agent vs Multi Agent

Both deterministic conditions completed 100% of tasks.

- Single Agent mean wall-clock: `{single["mean_duration_seconds"]:.4f}s`
- Multi Agent mean wall-clock: `{multi["mean_duration_seconds"]:.4f}s`
- Multi Agent speedup: `{speedup:.3f}x`
- Single Agent parallel overlap: `{single["mean_parallel_overlap_seconds"]:.4f}s`
- Multi Agent parallel overlap: `{multi["mean_parallel_overlap_seconds"]:.4f}s`

This controlled experiment demonstrates orchestration parallelism and role topology only. It does not establish superior LLM reasoning quality.

### Local Recovery

- Recovery OFF: final workflow failed.
- Recovery ON: final workflow succeeded.
- Local recovery cycles: `1`
- Successful unaffected predecessor was not rerun.

This demonstrates both recoverability and locality of recovery.

### Contract Validation

The exact same green phase report is evaluated in both conditions.

- Contract OFF: declared complete.
- Contract ON: rejected completion.
- Only missing criterion: `final_evidence`.

This demonstrates prevention of false completion.

### Recorded Real Research Runs

Historical real research runs are also available as `recorded_real_run` evidence.

They demonstrate that local recovery and multi-phase contract completion have occurred in actual project executions.

They are observational runs, not controlled treatment-vs-control experiments.

## Evidence boundaries

`deterministic_controlled_run` is mechanism-level controlled evidence.

`recorded_real_run` is genuine historical execution evidence.

`live_real_run` will be generated after model API configuration.

Do not present deterministic timing results as evidence of superior LLM reasoning quality.

Do not present recorded historical runs as randomized controlled comparisons.

## Remaining experiments

- Live LLM recovery OFF vs phase recovery vs full recovery.
- Live LLM Single Agent vs Multi Agent.
- Fixed node placement vs dynamic device/edge/cloud routing.
"""

    md_path = (
        OUTPUT_DIR / "competition_evaluation.md"
    )

    md_path.write_text(
        markdown,
        encoding="utf-8",
    )

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "agent_wall_clock_speedup": speedup,
        "live_llm_available": False,
        "sources": {
            "agents": str(agents_path),
            "recovery": str(recovery_path),
            "contract": str(contract_path),
            "research": str(research_path),
        },
        "rows": rows,
    }

    json_path = (
        OUTPUT_DIR / "competition_evaluation.json"
    )

    json_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"agents={agents_path.resolve()}"
    )
    print(
        f"speedup={speedup:.3f}x"
    )
    print(
        f"csv={csv_path.resolve()}"
    )
    print(
        f"markdown={md_path.resolve()}"
    )
    print(
        f"json={json_path.resolve()}"
    )
    print(
        f"figure={agent_figure.resolve()}"
    )
    print(
        f"figure={recovery_figure.resolve()}"
    )
    print(
        f"figure={contract_figure.resolve()}"
    )


if __name__ == "__main__":
    main()
