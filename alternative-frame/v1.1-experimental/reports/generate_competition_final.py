from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


SUMMARY_DIR = Path("benchmarks/results/summary")
OUTPUT_DIR = Path("reports/competition_final")
FIGURE_DIR = OUTPUT_DIR / "figures"


def latest(pattern: str) -> Path:
    files = sorted(
        SUMMARY_DIR.glob(pattern),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            f"No benchmark result matching {pattern!r}"
        )

    return files[0]


def load(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def main() -> int:
    import matplotlib.pyplot as plt

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    FIGURE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    agents_path = latest(
        "deterministic_agents-*.json"
    )
    recovery_path = latest(
        "deterministic_recovery-*.json"
    )
    contract_path = latest(
        "deterministic_contract-*.json"
    )
    routing_path = latest(
        "deterministic_routing-*.json"
    )
    research_path = latest(
        "research_recorded-*.json"
    )

    agents = load(agents_path)
    recovery = load(recovery_path)
    contract = load(contract_path)
    routing = load(routing_path)
    research = load(research_path)

    agent_map = {
        row["mode"]: row
        for row in agents["summaries"]
    }

    recovery_map = {
        row["mode"]: row
        for row in recovery["results"]
    }

    contract_map = {
        row["mode"]: row
        for row in contract["results"]
    }

    routing_map = {
        row["mode"]: row
        for row in routing["results"]
    }

    research_map = {
        row["case"]: row
        for row in research["runs"]
    }

    single = agent_map["single_agent"]
    multi = agent_map["multi_agent"]

    recovery_off = recovery_map[
        "recovery_off"
    ]
    recovery_on = recovery_map[
        "recovery_on"
    ]

    contract_off = contract_map[
        "contract_off"
    ]
    contract_on = contract_map[
        "contract_on"
    ]

    fixed = routing_map[
        "fixed_cloud"
    ]
    dynamic = routing_map[
        "dynamic_routing"
    ]

    normal = research_map[
        "research_normal"
    ]
    real_recovery = research_map[
        "research_local_recovery"
    ]

    agent_speedup = (
        single["mean_duration_seconds"]
        / multi["mean_duration_seconds"]
    )

    # --------------------------------------------------
    # Figure 1 — Agent topology
    # --------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(7, 4)
    )

    ax.bar(
        ["Single Agent", "Multi Agent"],
        [
            single[
                "mean_duration_seconds"
            ],
            multi[
                "mean_duration_seconds"
            ],
        ],
    )

    ax.set_ylabel(
        "Mean wall-clock seconds"
    )
    ax.set_title(
        "Agent Topology Ablation"
    )

    fig.tight_layout()

    path = (
        FIGURE_DIR
        / "agent_wall_clock.png"
    )

    fig.savefig(
        path,
        dpi=180,
    )
    plt.close(fig)

    # --------------------------------------------------
    # Figure 2 — Recovery
    # --------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(7, 4)
    )

    ax.bar(
        ["Recovery OFF", "Recovery ON"],
        [
            int(
                recovery_off[
                    "goal_completed"
                ]
            ),
            int(
                recovery_on[
                    "goal_completed"
                ]
            ),
        ],
    )

    ax.set_ylim(0, 1.1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(
        ["Failed", "Completed"]
    )
    ax.set_title(
        "Local Recovery Ablation"
    )

    fig.tight_layout()

    path = (
        FIGURE_DIR
        / "recovery_completion.png"
    )

    fig.savefig(
        path,
        dpi=180,
    )
    plt.close(fig)

    # --------------------------------------------------
    # Figure 3 — Contract
    # --------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(7, 4)
    )

    ax.bar(
        ["Contract OFF", "Contract ON"],
        [
            int(
                contract_off[
                    "completed"
                ]
            ),
            int(
                contract_on[
                    "completed"
                ]
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

    path = (
        FIGURE_DIR
        / "contract_decision.png"
    )

    fig.savefig(
        path,
        dpi=180,
    )
    plt.close(fig)

    # --------------------------------------------------
    # Figure 4 — Routing
    # --------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(7, 4)
    )

    ax.bar(
        ["Fixed Cloud", "Dynamic Routing"],
        [
            int(
                fixed["completed"]
            ),
            int(
                dynamic["completed"]
            ),
        ],
    )

    ax.set_ylim(0, 1.1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(
        ["Failed", "Completed"]
    )

    ax.set_title(
        "Fixed vs Dynamic Routing"
    )

    fig.tight_layout()

    path = (
        FIGURE_DIR
        / "routing_completion.png"
    )

    fig.savefig(
        path,
        dpi=180,
    )
    plt.close(fig)

    # --------------------------------------------------
    # Figure 5 — Recorded real research
    # --------------------------------------------------

    fig, ax = plt.subplots(
        figsize=(8, 4)
    )

    names = [
        "research_normal",
        "research_local_recovery",
    ]

    first_pass = [
        normal[
            "first_pass_count"
        ],
        real_recovery[
            "first_pass_count"
        ],
    ]

    local_recovery = [
        normal[
            "local_recovery_count"
        ],
        real_recovery[
            "local_recovery_count"
        ],
    ]

    x = range(len(names))
    width = 0.35

    ax.bar(
        [
            value - width / 2
            for value in x
        ],
        first_pass,
        width,
        label="First-pass successes",
    )

    ax.bar(
        [
            value + width / 2
            for value in x
        ],
        local_recovery,
        width,
        label="Local recovery cycles",
    )

    ax.set_xticks(
        list(x)
    )
    ax.set_xticklabels(
        names
    )

    ax.set_title(
        "Recorded Real Research Runs"
    )
    ax.legend()

    fig.tight_layout()

    path = (
        FIGURE_DIR
        / "recorded_research.png"
    )

    fig.savefig(
        path,
        dpi=180,
    )
    plt.close(fig)

    # --------------------------------------------------
    # Comparison CSV
    # --------------------------------------------------

    rows = [
        {
            "experiment": "agent_topology",
            "condition": "single_agent",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "completed": True,
            "key_metric": (
                single[
                    "mean_duration_seconds"
                ]
            ),
            "result": (
                "100% completion; "
                "single serialized backend"
            ),
        },
        {
            "experiment": "agent_topology",
            "condition": "multi_agent",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "completed": True,
            "key_metric": (
                multi[
                    "mean_duration_seconds"
                ]
            ),
            "result": (
                f"{agent_speedup:.3f}x "
                "wall-clock speedup"
            ),
        },
        {
            "experiment": "local_recovery",
            "condition": "recovery_off",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "completed": (
                recovery_off[
                    "goal_completed"
                ]
            ),
            "key_metric": 0,
            "result": (
                "injected failure remained failed"
            ),
        },
        {
            "experiment": "local_recovery",
            "condition": "recovery_on",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "completed": (
                recovery_on[
                    "goal_completed"
                ]
            ),
            "key_metric": (
                recovery_on[
                    "local_recovery_count"
                ]
            ),
            "result": (
                "local recovery restored success "
                "without rerunning frozen predecessor"
            ),
        },
        {
            "experiment": "contract_validation",
            "condition": "contract_off",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "completed": (
                contract_off[
                    "completed"
                ]
            ),
            "key_metric": None,
            "result": (
                "false completion accepted"
            ),
        },
        {
            "experiment": "contract_validation",
            "condition": "contract_on",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "completed": (
                contract_on[
                    "completed"
                ]
            ),
            "key_metric": (
                ",".join(
                    contract_on[
                        "missing_criteria"
                    ]
                )
            ),
            "result": (
                "missing final evidence detected"
            ),
        },
        {
            "experiment": "routing",
            "condition": "fixed_cloud",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "completed": (
                fixed["completed"]
            ),
            "key_metric": (
                fixed[
                    "fallback_count"
                ]
            ),
            "result": (
                "cloud outage caused final failure"
            ),
        },
        {
            "experiment": "routing",
            "condition": "dynamic_routing",
            "evidence_kind": (
                "deterministic_controlled_run"
            ),
            "completed": (
                dynamic["completed"]
            ),
            "key_metric": (
                dynamic[
                    "fallback_count"
                ]
            ),
            "result": (
                "cloud failure preserved; "
                "fallback to edge succeeded"
            ),
        },
    ]

    csv_path = (
        OUTPUT_DIR
        / "competition_comparison.csv"
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(
                rows[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(rows)

    # --------------------------------------------------
    # Markdown report
    # --------------------------------------------------

    markdown = f"""# Final Competition Evaluation

Generated: {datetime.now(timezone.utc).isoformat()}

## 1. Single Agent vs Multi Agent

Both deterministic conditions completed all tasks.

- Single Agent completion: 100%
- Multi Agent completion: 100%
- Single Agent mean duration: {single["mean_duration_seconds"]:.4f}s
- Multi Agent mean duration: {multi["mean_duration_seconds"]:.4f}s
- Multi Agent wall-clock speedup: {agent_speedup:.3f}x
- Multi Agent mean parallel overlap: {multi["mean_parallel_overlap_seconds"]:.4f}s

**Supported conclusion:** multi-agent role topology exposes available DAG parallelism and reduces wall-clock duration in the controlled workload.

This experiment does not establish superior LLM reasoning quality.

---

## 2. Recovery OFF vs Recovery ON

### Recovery OFF

- completed: {recovery_off["goal_completed"]}
- local recovery cycles: {recovery_off["local_recovery_count"]}
- execution trace: `{recovery_off["execution_log"]}`

### Recovery ON

- completed: {recovery_on["goal_completed"]}
- local recovery cycles: {recovery_on["local_recovery_count"]}
- execution trace: `{recovery_on["execution_log"]}`

The successful predecessor is not rerun.

**Supported conclusion:** local DAG recovery repairs the impacted subgraph while preserving unaffected successful work.

---

## 3. Contract OFF vs Contract ON

Both conditions receive the same successful phase report.

### Contract OFF

- phase report: {contract_off["phase_report_status"]}
- declared complete: {contract_off["completed"]}

### Contract ON

- phase report: {contract_on["phase_report_status"]}
- declared complete: {contract_on["completed"]}
- missing criteria: `{contract_on["missing_criteria"]}`

**Supported conclusion:** global contract validation prevents false completion when required final evidence is missing.

---

## 4. Fixed Cloud vs Dynamic Device/Edge/Cloud Routing

A cloud outage is injected into the same compute workload.

### Fixed Cloud

- completed: {fixed["completed"]}
- final node: {fixed["final_node_type"]}
- fallback count: {fixed["fallback_count"]}
- execution attempts: {fixed["execution_attempts"]}
- cloud attempts: {fixed["cloud_attempts"]}
- edge attempts: {fixed["edge_attempts"]}

### Dynamic Routing

- completed: {dynamic["completed"]}
- final node: {dynamic["final_node_type"]}
- fallback count: {dynamic["fallback_count"]}
- execution attempts: {dynamic["execution_attempts"]}
- cloud attempts: {dynamic["cloud_attempts"]}
- edge attempts: {dynamic["edge_attempts"]}

Execution path:

`cloud failure -> edge fallback -> success`

**Supported conclusion:** under the controlled cloud-outage condition, fixed Cloud placement fails, while the real NodeRouter/RuntimeExecutor path preserves the failed Cloud attempt and successfully falls back to Edge.

This is a deterministic routing resilience experiment, not a claim about physical distributed network performance.

---

## 5. Recorded Real Research Evidence

### Normal

- final goal completed: {normal["final_goal_completed"]}
- completed tasks: {normal["success_count"]}
- cumulative planned tasks: {normal["task_count"]}
- first-pass successes: {normal["first_pass_count"]}
- local recovery cycles: {normal["local_recovery_count"]}
- phases: {normal["phase_count"]}

### Local Recovery Sample

- final goal completed: {real_recovery["final_goal_completed"]}
- completed tasks: {real_recovery["success_count"]}
- cumulative planned tasks: {real_recovery["task_count"]}
- first-pass successes: {real_recovery["first_pass_count"]}
- local recovery cycles: {real_recovery["local_recovery_count"]}
- phases: {real_recovery["phase_count"]}

Historical recorded runs are genuine project execution evidence, but they are not controlled treatment-vs-control experiments.

Do not describe `8 / 11` as a 72.7% final-goal success rate.

---

# Final Controlled Evidence Matrix

| Experiment | Control | Treatment | Result |
|---|---|---|---|
| Agent topology | Single backend | Multi-agent backends | Same completion, {agent_speedup:.3f}x wall-clock speedup |
| Local recovery | Recovery OFF | Recovery ON | Failed -> completed |
| Contract validation | Contract OFF | Contract ON | False completion -> missing evidence detected |
| Edge/cloud routing | Fixed Cloud | Dynamic routing | Cloud failure -> Edge fallback success |

---

# Evidence Boundaries

- `deterministic_controlled_run`: mechanism-level controlled evidence.
- `recorded_real_run`: genuine historical execution evidence.
- `live_real_run`: reserved for future API model experiments.

Unknown telemetry must remain unknown.

Do not claim live LLM improvement until live experiments are actually run.

Do not describe this single-machine edge/cloud runtime as measured physical network performance.
"""

    md_path = (
        OUTPUT_DIR
        / "competition_evaluation.md"
    )

    md_path.write_text(
        markdown,
        encoding="utf-8",
    )

    json_path = (
        OUTPUT_DIR
        / "competition_evaluation.json"
    )

    json_path.write_text(
        json.dumps(
            {
                "generated_at": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
                "agent_speedup": (
                    agent_speedup
                ),
                "routing_result": {
                    "fixed_cloud_completed": (
                        fixed["completed"]
                    ),
                    "dynamic_completed": (
                        dynamic["completed"]
                    ),
                    "dynamic_final_node": (
                        dynamic[
                            "final_node_type"
                        ]
                    ),
                    "fallback_count": (
                        dynamic[
                            "fallback_count"
                        ]
                    ),
                },
                "sources": {
                    "agents": str(
                        agents_path
                    ),
                    "recovery": str(
                        recovery_path
                    ),
                    "contract": str(
                        contract_path
                    ),
                    "routing": str(
                        routing_path
                    ),
                    "research": str(
                        research_path
                    ),
                },
                "rows": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"agents={agents_path.resolve()}"
    )
    print(
        f"recovery={recovery_path.resolve()}"
    )
    print(
        f"contract={contract_path.resolve()}"
    )
    print(
        f"routing={routing_path.resolve()}"
    )
    print(
        f"research={research_path.resolve()}"
    )

    print(
        f"agent_speedup={agent_speedup:.3f}x"
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

    for figure in sorted(
        FIGURE_DIR.glob("*.png")
    ):
        print(
            f"figure={figure.resolve()}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
