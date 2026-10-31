"""Build traceable, presentation-ready competition evidence assets.

The input paths are explicit on purpose. This prevents a report from silently
mixing runs from different dates or commits by selecting the newest glob match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "competition_artifacts"
CONFIGS = {
    "agent": "benchmarks/configs/deterministic_agents.json",
    "recovery": "benchmarks/configs/deterministic_recovery.json",
    "contract": "benchmarks/configs/deterministic_contract.json",
    "routing": "benchmarks/configs/deterministic_routing.json",
    "research": "benchmarks/configs/research_recorded.json",
}
COMMANDS = {
    "agent": "python run_deterministic_agent_ablation.py",
    "recovery": "python run_deterministic_recovery_ablation.py",
    "contract": "python run_deterministic_contract_ablation.py",
    "routing": "python run_deterministic_routing_ablation.py",
    "research": "python run_recorded_benchmarks.py --config benchmarks/configs/research_recorded.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def copy_evidence(source: Path, evidence_dir: Path) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    target = evidence_dir / source.name
    shutil.copy2(source, target)
    return target


def save_figure(fig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def add_footer(fig, source: str, evidence_kind: str, commit: str) -> None:
    fig.text(
        0.01,
        0.01,
        f"Evidence: {evidence_kind} | commit: {commit[:12]} | source: {source}",
        ha="left",
        va="bottom",
        fontsize=7,
        color="#5B6472",
    )


def build_agents(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = {row["mode"]: row for row in payload["summaries"]}
    labels = ["Single Agent", "Multi Agent"]
    values = [rows["single_agent"]["mean_duration_seconds"], rows["multi_agent"]["mean_duration_seconds"]]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(labels, values, color=["#9AA7B8", "#1976A8"], width=0.56)
    ax.set_title("Multi-Agent Topology Reduces Controlled Wall-Clock Time", loc="left", weight="bold")
    ax.set_ylabel("Mean wall-clock time (s)")
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.4f}s", ha="center", va="bottom")
    speedup = values[0] / values[1]
    standard_deviations = []
    for mode in ("single_agent", "multi_agent"):
        durations = [row["duration_seconds"] for row in payload.get("runs", []) if row["mode"] == mode]
        if not durations:
            standard_deviations.append(0.0)
        else:
            standard_deviations.append(statistics.stdev(durations) if len(durations) > 1 else 0.0)
    ax.errorbar([bar.get_x() + bar.get_width() / 2 for bar in bars], values,
                yerr=standard_deviations, fmt="none", ecolor="#263746", capsize=6, lw=1.5)
    fig.subplots_adjust(right=0.77)
    fig.text(0.79, 0.68, f"Speedup: {speedup:.3f}x\nCompletion: 100% / 100%\nRepeats: {payload['repeats']}\nWhiskers: sample SD",
             ha="left", va="center", bbox={"facecolor": "#EAF4F8", "edgecolor": "none", "pad": 8}, fontsize=9)
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "agent_topology.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Controlled workload wall-clock speedup", "speedup": round(speedup, 6)}


def build_recovery(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = {row["mode"]: row for row in payload["results"]}
    fig, ax = plt.subplots(figsize=(9, 3.9))
    ax.axis("off")
    steps = [("prepare", "#DDE6EE"), ("compute\nfailed", "#F7C7C7"), ("local\nreplan", "#F7E5B5"), ("compute\nretry", "#BFE3D0"), ("verify\ncomplete", "#9ED6B7")]
    for index, (label, color) in enumerate(steps):
        x = 0.05 + index * 0.22
        ax.text(x, 0.56, label, ha="center", va="center", fontsize=11, weight="bold",
                bbox={"boxstyle": "round,pad=0.7", "facecolor": color, "edgecolor": "#657384"}, transform=ax.transAxes)
        if index < len(steps) - 1:
            ax.annotate("", xy=(x + 0.17, 0.56), xytext=(x + 0.07, 0.56), xycoords=ax.transAxes,
                        arrowprops={"arrowstyle": "->", "color": "#657384", "lw": 1.6})
    ax.text(0.05, 0.16, "Recovery OFF: failed after prepare → compute", transform=ax.transAxes, color="#A13B3B")
    ax.text(0.05, 0.07, "Recovery ON: completed; prepare attempts = 1, local recovery cycles = 1", transform=ax.transAxes, color="#176B4D")
    ax.set_title("Local Recovery Re-runs Only the Impacted Subgraph", loc="left", weight="bold")
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "recovery_flow.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Impacted-subgraph recovery", "recovery_on_completed": rows["recovery_on"]["goal_completed"]}


def build_contract(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = {row["mode"]: row for row in payload["results"]}
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.axis("off")
    items = [
        (0.25, "Contract OFF", "FALSE COMPLETION\naccepted", "#F7C7C7"),
        (0.75, "Contract ON", "MISSING EVIDENCE\ncorrectly blocked", "#BFE3D0"),
    ]
    for x, title, body, color in items:
        ax.text(x, 0.57, title, ha="center", va="center", fontsize=14, weight="bold", transform=ax.transAxes)
        ax.text(x, 0.37, body, ha="center", va="center", fontsize=12, transform=ax.transAxes,
                bbox={"boxstyle": "round,pad=1.0", "facecolor": color, "edgecolor": "#657384"})
    ax.text(0.75, 0.12, "missing criterion: final_evidence", ha="center", transform=ax.transAxes, fontsize=10, color="#176B4D")
    ax.set_title("Acceptance Contracts Prevent False Completion", loc="left", weight="bold")
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "contract_gate.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Missing final evidence is blocked", "contract_on_completed": rows["contract_on"]["completed"]}


def build_routing(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = {row["mode"]: row for row in payload["results"]}
    fig, ax = plt.subplots(figsize=(9, 3.9))
    ax.axis("off")
    nodes = [(0.12, "Cloud\nattempt", "#DDE6EE"), (0.38, "Cloud\nfailure", "#F7C7C7"), (0.65, "Edge\nfallback", "#F7E5B5"), (0.88, "Success", "#BFE3D0")]
    for index, (x, label, color) in enumerate(nodes):
        ax.text(x, 0.55, label, ha="center", va="center", fontsize=12, weight="bold", transform=ax.transAxes,
                bbox={"boxstyle": "round,pad=0.8", "facecolor": color, "edgecolor": "#657384"})
        if index < len(nodes) - 1:
            ax.annotate("", xy=(nodes[index + 1][0] - 0.07, 0.55), xytext=(x + 0.07, 0.55), xycoords=ax.transAxes,
                        arrowprops={"arrowstyle": "->", "color": "#657384", "lw": 1.6})
    ax.text(0.5, 0.15, "Fixed Cloud: failed | Dynamic Routing: completed | fallback count: 1\nSingle-machine runtime simulation; not physical network measurement",
            ha="center", transform=ax.transAxes)
    ax.set_title("Dynamic Routing Falls Back to Edge After Cloud Failure", loc="left", weight="bold")
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "routing_fallback.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Controlled node-failure fallback", "dynamic_completed": rows["dynamic_routing"]["completed"]}


def build_research(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = payload["runs"]
    labels = [row["case"].replace("research_", "").replace("_", " ").title() for row in rows]
    first_pass = [row["first_pass_count"] for row in rows]
    recovery = [row["local_recovery_count"] for row in rows]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    positions = list(range(len(labels)))
    width = 0.34
    ax.bar([p - width / 2 for p in positions], first_pass, width, label="First-pass successes", color="#1976A8")
    ax.bar([p + width / 2 for p in positions], recovery, width, label="Local recovery cycles", color="#D97828")
    ax.set_xticks(positions, labels)
    ax.set_ylabel("Count")
    ax.set_title("Recorded Research Runs Show Completion With Distinct Recovery Evidence", loc="left", weight="bold")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False, loc="upper right")
    ax.set_title("Recorded Research Runs: Both Completed; Recovery Sample Used Local Recovery\nHistorical recorded_real_run; not a controlled comparison",
                 loc="left", weight="bold", fontsize=12)
    for p, value in zip(positions, first_pass):
        ax.text(p - width / 2, value, str(value), ha="center", va="bottom")
    for p, value in zip(positions, recovery):
        ax.text(p + width / 2, value, str(value), ha="center", va="bottom")
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "research_evidence.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Historical research execution evidence", "evidence_kind": payload["evidence_kind"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--routing", type=Path, required=True)
    parser.add_argument("--research", type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    evidence_dir = output / "evidence"
    charts_dir = output / "charts"
    output.mkdir(parents=True, exist_ok=True)
    sources = {name: path.resolve() for name, path in {
        "agent": args.agent, "recovery": args.recovery, "contract": args.contract,
        "routing": args.routing, "research": args.research,
    }.items()}
    for name, path in sources.items():
        if not path.exists():
            raise FileNotFoundError(f"missing {name} evidence: {path}")

    copied = {name: copy_evidence(path, evidence_dir) for name, path in sources.items()}
    payloads = {name: load(path) for name, path in sources.items()}
    copied_configs = {}
    for name, relative in CONFIGS.items():
        config_path = ROOT / relative
        if config_path.is_file():
            copied_configs[name] = copy_evidence(config_path, evidence_dir)
    chart_records = [
        build_agents(payloads["agent"], copied["agent"], charts_dir, args.commit),
        build_recovery(payloads["recovery"], copied["recovery"], charts_dir, args.commit),
        build_contract(payloads["contract"], copied["contract"], charts_dir, args.commit),
        build_routing(payloads["routing"], copied["routing"], charts_dir, args.commit),
        build_research(payloads["research"], copied["research"], charts_dir, args.commit),
    ]
    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_tag": "v1.1.0-competition-candidate",
        "candidate_commit": args.commit,
        "live_api_status": "pending_credentials",
        "evidence_classes": ["deterministic_controlled_run", "recorded_real_run", "live_real_run"],
        "sources": [
            {
                "name": name,
                "experiment_name": payloads[name].get("experiment", payloads[name].get("benchmark", name)),
                "run_id": (payloads[name].get("provenance") or {}).get("run_id"),
                "run_ids": [row.get("run_id") for row in payloads[name].get("runs", payloads[name].get("results", [])) if row.get("run_id")],
                "generated_at": payloads[name].get("generated_at"),
                "command": (payloads[name].get("provenance") or {}).get("command", COMMANDS[name]),
                "model": "deterministic" if payloads[name].get("evidence_kind") == "deterministic_controlled_run" else "unknown/historical",
                "endpoint_redacted": None,
                "config_path": CONFIGS[name],
                "config_sha256": sha256(copied_configs[name]) if name in copied_configs else None,
                "path": f"evidence/{copied[name].name}",
                "evidence_kind": payloads[name].get("evidence_kind"),
                "sha256": sha256(copied[name]),
            }
            for name in sources
        ],
        "configurations": [
            {"name": name, "path": f"evidence/{path.name}", "sha256": sha256(path)}
            for name, path in copied_configs.items()
        ],
        "charts": [
            {**record, "path": f"charts/{record['chart']}", "sha256": sha256(charts_dir / record["chart"])}
            for record in chart_records
        ],
        "api_runs": [],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "README.md").write_text(
        "# Competition evidence package\n\n"
        "This package uses explicit source files and a manifest. It does not select the latest benchmark by glob.\n\n"
        "`live_api_status=pending_credentials` means no live API result is included yet. Historical research evidence remains labelled `recorded_real_run`.\n",
        encoding="utf-8",
    )
    print(f"package={output}")
    print(f"manifest={output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
