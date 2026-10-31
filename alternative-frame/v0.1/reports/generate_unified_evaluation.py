from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


SUMMARY_DIR = Path("benchmarks/results/summary")
OUTPUT_DIR = Path("reports/unified_evaluation")
FIGURE_DIR = OUTPUT_DIR / "figures"


def latest(pattern: str) -> Path:
    matches = sorted(
        SUMMARY_DIR.glob(pattern),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(
            f"No benchmark result matching {pattern!r}"
        )
    return matches[0]


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def research_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []

    for item in payload["runs"]:
        rows.append(
            {
                "experiment": "recorded_research",
                "case": item["case"],
                "evidence_kind": "recorded_real_run",
                "goal_completed": item["final_goal_completed"],
                "status": item["status"],
                "task_count": item["task_count"],
                "success_count": item["success_count"],
                "first_pass_count": item["first_pass_count"],
                "local_recovery_count": item["local_recovery_count"],
                "phase_count": item["phase_count"],
                "extra_planned_tasks": max(
                    item["task_count"] - item["success_count"],
                    0,
                ),
                "false_completion_detected": None,
                "missing_criteria": None,
                "duration_seconds": item.get("duration_seconds"),
            }
        )

    return rows


def recovery_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []

    for item in payload["results"]:
        rows.append(
            {
                "experiment": "local_recovery_ablation",
                "case": item["mode"],
                "evidence_kind": payload["evidence_kind"],
                "goal_completed": item["goal_completed"],
                "status": item["status"],
                "task_count": item["original_task_count"],
                "success_count": item["final_success_count"],
                "first_pass_count": None,
                "local_recovery_count": item["local_recovery_count"],
                "phase_count": 1,
                "extra_planned_tasks": item["extra_executions"],
                "false_completion_detected": None,
                "missing_criteria": None,
                "duration_seconds": None,
            }
        )

    return rows


def contract_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []

    for item in payload["results"]:
        rows.append(
            {
                "experiment": "contract_ablation",
                "case": item["mode"],
                "evidence_kind": payload["evidence_kind"],
                "goal_completed": item["completed"],
                "status": item["phase_report_status"],
                "task_count": None,
                "success_count": None,
                "first_pass_count": None,
                "local_recovery_count": 0,
                "phase_count": 1,
                "extra_planned_tasks": 0,
                "false_completion_detected": (
                    item["mode"] == "contract_on"
                    and not item["completed"]
                    and item["phase_report_status"] == "success"
                ),
                "missing_criteria": ",".join(
                    item.get("missing_criteria") or []
                ),
                "duration_seconds": None,
            }
        )

    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
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


def plot_recovery(payload: Dict[str, Any]) -> str:
    import matplotlib.pyplot as plt

    items = {
        item["mode"]: item
        for item in payload["results"]
    }

    modes = ["recovery_off", "recovery_on"]

    success = [
        1 if items[m]["goal_completed"] else 0
        for m in modes
    ]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(modes, success)
    ax.set_ylim(0, 1.1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Failed", "Completed"])
    ax.set_ylabel("Final outcome")
    ax.set_title("Controlled Local-Recovery Ablation")
    fig.tight_layout()

    path = FIGURE_DIR / "recovery_completion.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)

    return str(path)


def plot_recovery_execution(payload: Dict[str, Any]) -> str:
    import matplotlib.pyplot as plt

    items = {
        item["mode"]: item
        for item in payload["results"]
    }

    modes = ["recovery_off", "recovery_on"]

    executions = [
        len(items[m]["execution_log"])
        for m in modes
    ]

    recoveries = [
        items[m]["local_recovery_count"]
        for m in modes
    ]

    x = range(len(modes))
    width = 0.35

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.bar(
        [i - width / 2 for i in x],
        executions,
        width,
        label="Task executions",
    )

    ax.bar(
        [i + width / 2 for i in x],
        recoveries,
        width,
        label="Local recovery cycles",
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(modes)
    ax.set_ylabel("Count")
    ax.set_title("Recovery Cost and Locality")
    ax.legend()

    fig.tight_layout()

    path = FIGURE_DIR / "recovery_execution_cost.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)

    return str(path)


def plot_contract(payload: Dict[str, Any]) -> str:
    import matplotlib.pyplot as plt

    items = {
        item["mode"]: item
        for item in payload["results"]
    }

    modes = ["contract_off", "contract_on"]

    completed = [
        1 if items[m]["completed"] else 0
        for m in modes
    ]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(modes, completed)

    ax.set_ylim(0, 1.1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(
        ["Rejected / incomplete", "Declared complete"]
    )

    ax.set_ylabel("Completion decision")
    ax.set_title("Contract Validation Ablation")

    fig.tight_layout()

    path = FIGURE_DIR / "contract_completion_decision.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)

    return str(path)


def plot_recorded_research(payload: Dict[str, Any]) -> str:
    import matplotlib.pyplot as plt

    names = []
    first_pass = []
    recovery = []

    for item in payload["runs"]:
        names.append(item["case"])
        first_pass.append(item["first_pass_count"])
        recovery.append(item["local_recovery_count"])

    x = range(len(names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4))

    ax.bar(
        [i - width / 2 for i in x],
        first_pass,
        width,
        label="First-pass successes",
    )

    ax.bar(
        [i + width / 2 for i in x],
        recovery,
        width,
        label="Local recovery cycles",
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(names)
    ax.set_ylabel("Count")
    ax.set_title("Recorded Real Research Runs")
    ax.legend()

    fig.tight_layout()

    path = FIGURE_DIR / "recorded_research.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)

    return str(path)


def build_markdown(
    research: Dict[str, Any],
    recovery: Dict[str, Any],
    contract: Dict[str, Any],
    sources: Dict[str, str],
) -> str:

    recovery_map = {
        item["mode"]: item
        for item in recovery["results"]
    }

    contract_map = {
        item["mode"]: item
        for item in contract["results"]
    }

    research_map = {
        item["case"]: item
        for item in research["runs"]
    }

    off = recovery_map["recovery_off"]
    on = recovery_map["recovery_on"]

    contract_off = contract_map["contract_off"]
    contract_on = contract_map["contract_on"]

    normal = research_map["research_normal"]
    recorded_recovery = research_map[
        "research_local_recovery"
    ]

    return f"""# Unified Evaluation Report

Generated: {datetime.now(timezone.utc).isoformat()}

## Evidence classes

This report deliberately separates three evidence classes.

1. `deterministic_controlled_run`
   - controlled mechanism-level ablation;
   - identical inputs and deterministic failures;
   - no LLM API required.

2. `recorded_real_run`
   - previously recorded real research-demo executions;
   - reflects genuine project execution history;
   - not a controlled randomized comparison.

3. `live_real_run`
   - reserved for future live model experiments after an API model is configured;
   - no live-model claims are made in this report yet.

## 1. Controlled local-recovery ablation

The same three-node DAG is executed in both conditions:

`prepare -> compute -> verify`

The first execution of `compute` fails deterministically.

| Mode | Final result | Local recovery | Execution trace |
|---|---|---:|---|
| recovery_off | {"PASS" if off["goal_completed"] else "FAIL"} | {off["local_recovery_count"]} | `{off["execution_log"]}` |
| recovery_on | {"PASS" if on["goal_completed"] else "FAIL"} | {on["local_recovery_count"]} | `{on["execution_log"]}` |

### Finding

Recovery disabled leaves the workflow failed after the injected computation failure.

Recovery enabled performs one local recovery cycle and completes the workflow.

The successful `prepare` predecessor is not rerun. Only the impacted `compute` node and blocked downstream `verify` node are executed during recovery.

Therefore this experiment demonstrates both **recoverability** and **recovery locality**.

## 2. Controlled contract-validation ablation

Both modes receive the same green phase report.

`calculator.py` exists with artifact provenance and the exact required test command has successful exit-code-0 evidence.

`FINAL_EVIDENCE.md` is deliberately omitted.

| Mode | Phase report | Completion decision | Missing criteria |
|---|---|---|---|
| contract_off | {contract_off["phase_report_status"]} | {contract_off["completed"]} | {contract_off["missing_criteria"]} |
| contract_on | {contract_on["phase_report_status"]} | {contract_on["completed"]} | {contract_on["missing_criteria"]} |

### Finding

Without global contract validation, a successful phase report is declared complete.

With contract validation enabled, the same execution is correctly rejected because `final_evidence` is missing.

This demonstrates that contract validation prevents **false completion** rather than merely checking whether individual agents returned `success`.

## 3. Recorded real research runs

| Run | Final goal | Completed | Cumulative planned | First-pass | Local recovery | Phases |
|---|---|---:|---:|---:|---:|---:|
| research_normal | {normal["final_goal_completed"]} | {normal["success_count"]} | {normal["task_count"]} | {normal["first_pass_count"]} | {normal["local_recovery_count"]} | {normal["phase_count"]} |
| research_local_recovery | {recorded_recovery["final_goal_completed"]} | {recorded_recovery["success_count"]} | {recorded_recovery["task_count"]} | {recorded_recovery["first_pass_count"]} | {recorded_recovery["local_recovery_count"]} | {recorded_recovery["phase_count"]} |

### Finding

Both historical research runs eventually completed the final goal.

The local-recovery run contains one real local-recovery event and accumulated additional planned work.

`8 / 11` must **not** be described as a 72.7% final-goal success rate. The denominator includes recovery-introduced work, while the final goal itself completed.

## 4. Current evidence summary

| Claim | Evidence |
|---|---|
| Local recovery can repair an injected DAG failure | deterministic controlled ablation |
| Local recovery avoids rerunning a successful unaffected predecessor | deterministic execution trace |
| Contract validation can prevent false completion | deterministic controlled ablation |
| Local recovery has occurred in a real research run | recorded real run |
| Multi-phase contract completion has occurred in real research runs | recorded real run |
| Live LLM recovery improves completion rate | **not yet established** |
| Single-agent vs multi-agent advantage | **not yet established** |
| Dynamic device/edge/cloud advantage | **not yet established** |

## 5. Measurement caveats

- Missing token usage is `unknown`, not zero.
- Missing model cost is `unknown`, not zero.
- Historical research samples do not contain reliable device/edge/cloud placement evidence.
- Recorded historical runs are observational evidence, not controlled treatment-vs-control experiments.
- Deterministic experiments isolate mechanism behavior but should not be presented as live LLM performance measurements.
- Live model ablations will be added once model API access is available.

## Source benchmark files

- Recorded research: `{sources["research"]}`
- Recovery ablation: `{sources["recovery"]}`
- Contract ablation: `{sources["contract"]}`
"""


def main() -> int:
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

    research = load_json(research_path)
    recovery = load_json(recovery_path)
    contract = load_json(contract_path)

    rows = (
        research_rows(research)
        + recovery_rows(recovery)
        + contract_rows(contract)
    )

    csv_path = (
        OUTPUT_DIR / "unified_comparison.csv"
    )
    json_path = (
        OUTPUT_DIR / "unified_evaluation.json"
    )
    md_path = (
        OUTPUT_DIR / "unified_evaluation.md"
    )

    write_csv(csv_path, rows)

    figures = [
        plot_recovery(recovery),
        plot_recovery_execution(recovery),
        plot_contract(contract),
        plot_recorded_research(research),
    ]

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "evidence_classes": [
            "deterministic_controlled_run",
            "recorded_real_run",
        ],
        "live_real_run_available": False,
        "sources": {
            "research": str(research_path),
            "recovery": str(recovery_path),
            "contract": str(contract_path),
        },
        "rows": rows,
        "figures": figures,
    }

    json_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path.write_text(
        build_markdown(
            research,
            recovery,
            contract,
            payload["sources"],
        ),
        encoding="utf-8",
    )

    print(
        f"research={research_path.resolve()}"
    )
    print(
        f"recovery={recovery_path.resolve()}"
    )
    print(
        f"contract={contract_path.resolve()}"
    )
    print(
        f"csv={csv_path.resolve()}"
    )
    print(
        f"json={json_path.resolve()}"
    )
    print(
        f"markdown={md_path.resolve()}"
    )

    for figure in figures:
        print(
            f"figure={Path(figure).resolve()}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
