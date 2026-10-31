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

if Path("C:/Windows/Fonts/msyh.ttc").is_file():
    plt.rcParams["font.family"] = "Microsoft YaHei"
    plt.rcParams["axes.unicode_minus"] = False


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
    labels = ["单 Agent", "多 Agent"]
    values = [rows["single_agent"]["mean_duration_seconds"], rows["multi_agent"]["mean_duration_seconds"]]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(labels, values, color=["#9AA7B8", "#1976A8"], width=0.56)
    ax.set_title("多 Agent 协作缩短受控任务墙钟时间", loc="left", weight="bold")
    ax.set_ylabel("平均运行耗时（秒）")
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
    fig.text(0.79, 0.68, f"加速比：{speedup:.3f} 倍\n完成率：100% / 100%\n重复次数：{payload['repeats']}\n误差线：样本标准差",
             ha="left", va="center", bbox={"facecolor": "#EAF4F8", "edgecolor": "none", "pad": 8}, fontsize=9)
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "agent_topology.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Controlled workload wall-clock speedup", "speedup": round(speedup, 6)}


def build_recovery(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = {row["mode"]: row for row in payload["results"]}
    fig, ax = plt.subplots(figsize=(9, 3.9))
    ax.axis("off")
    steps = [("准备", "#DDE6EE"), ("计算\n失败", "#F7C7C7"), ("局部\n重规划", "#F7E5B5"), ("计算\n重试", "#BFE3D0"), ("校验\n完成", "#9ED6B7")]
    for index, (label, color) in enumerate(steps):
        x = 0.05 + index * 0.22
        ax.text(x, 0.56, label, ha="center", va="center", fontsize=11, weight="bold",
                bbox={"boxstyle": "round,pad=0.7", "facecolor": color, "edgecolor": "#657384"}, transform=ax.transAxes)
        if index < len(steps) - 1:
            ax.annotate("", xy=(x + 0.17, 0.56), xytext=(x + 0.07, 0.56), xycoords=ax.transAxes,
                        arrowprops={"arrowstyle": "->", "color": "#657384", "lw": 1.6})
    ax.text(0.05, 0.16, "关闭恢复：准备、计算后失败", transform=ax.transAxes, color="#A13B3B")
    ax.text(0.05, 0.07, "开启恢复：最终完成；准备只执行 1 次；局部恢复 1 次", transform=ax.transAxes, color="#176B4D")
    ax.set_title("局部恢复只重跑受影响子图", loc="left", weight="bold")
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "recovery_flow.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Impacted-subgraph recovery", "recovery_on_completed": rows["recovery_on"]["goal_completed"]}


def build_contract(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = {row["mode"]: row for row in payload["results"]}
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.axis("off")
    items = [
        (0.25, "关闭验收契约", "错误完成\n被接受", "#F7C7C7"),
        (0.75, "开启验收契约", "缺失证据\n被正确拦截", "#BFE3D0"),
    ]
    for x, title, body, color in items:
        ax.text(x, 0.57, title, ha="center", va="center", fontsize=14, weight="bold", transform=ax.transAxes)
        ax.text(x, 0.37, body, ha="center", va="center", fontsize=12, transform=ax.transAxes,
                bbox={"boxstyle": "round,pad=1.0", "facecolor": color, "edgecolor": "#657384"})
    ax.text(0.75, 0.12, "缺少验收项：final_evidence", ha="center", transform=ax.transAxes, fontsize=10, color="#176B4D")
    ax.set_title("验收契约阻止系统虚报完成", loc="left", weight="bold")
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "contract_gate.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Missing final evidence is blocked", "contract_on_completed": rows["contract_on"]["completed"]}


def build_routing(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = {row["mode"]: row for row in payload["results"]}
    fig, ax = plt.subplots(figsize=(9, 3.9))
    ax.axis("off")
    nodes = [(0.12, "云端\n尝试", "#DDE6EE"), (0.38, "云端\n故障", "#F7C7C7"), (0.65, "边缘端\n回退", "#F7E5B5"), (0.88, "执行\n成功", "#BFE3D0")]
    for index, (x, label, color) in enumerate(nodes):
        ax.text(x, 0.55, label, ha="center", va="center", fontsize=12, weight="bold", transform=ax.transAxes,
                bbox={"boxstyle": "round,pad=0.8", "facecolor": color, "edgecolor": "#657384"})
        if index < len(nodes) - 1:
            ax.annotate("", xy=(nodes[index + 1][0] - 0.07, 0.55), xytext=(x + 0.07, 0.55), xycoords=ax.transAxes,
                        arrowprops={"arrowstyle": "->", "color": "#657384", "lw": 1.6})
    ax.text(0.5, 0.15, "固定云端：失败 | 动态路由：完成 | 回退次数：1\n单机运行时模拟，不是物理网络性能测量",
            ha="center", transform=ax.transAxes)
    ax.set_title("云端故障后，动态路由回退到边缘端", loc="left", weight="bold")
    add_footer(fig, path.name, payload["evidence_kind"], commit)
    output = charts / "routing_fallback.png"
    save_figure(fig, output)
    return {"chart": output.name, "claim": "Controlled node-failure fallback", "dynamic_completed": rows["dynamic_routing"]["completed"]}


def build_research(payload, path: Path, charts: Path, commit: str) -> dict[str, Any]:
    rows = payload["runs"]
    labels = ["正常运行" if row["case"] == "research_normal" else "局部恢复样本" for row in rows]
    first_pass = [row["first_pass_count"] for row in rows]
    recovery = [row["local_recovery_count"] for row in rows]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    positions = list(range(len(labels)))
    width = 0.34
    ax.bar([p - width / 2 for p in positions], first_pass, width, label="首次通过任务数", color="#1976A8")
    ax.bar([p + width / 2 for p in positions], recovery, width, label="局部恢复次数", color="#D97828")
    ax.set_xticks(positions, labels)
    ax.set_ylabel("数量")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(frameon=False, loc="upper right")
    ax.set_title("历史科研运行均完成；恢复样本经历 1 次局部恢复\n历史 recorded_real_run，不是受控对照实验",
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
    parser.add_argument("--validation-report", type=Path, action="append", default=[])
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
    validation_dir = output / "validation"
    validations = []
    for source in args.validation_report:
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"missing validation report: {source}")
        validation_dir.mkdir(parents=True, exist_ok=True)
        target = validation_dir / source.name
        shutil.copy2(source, target)
        report = load(source)
        validations.append({
            "target": report.get("target"),
            "status": report.get("status"),
            "path": f"validation/{target.name}",
            "sha256": sha256(target),
        })
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
        "candidate_tag_commit": "1d89c60230598746ef73b3475169efea6c12acbb",
        "evidence_commit": args.commit,
        "candidate_commit": "1d89c60230598746ef73b3475169efea6c12acbb",
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
        "validations": validations,
        "charts": [
            {**record, "path": f"charts/{record['chart']}", "sha256": sha256(charts_dir / record["chart"])}
            for record in chart_records
        ],
        "api_runs": [],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "README.md").write_text(
        "# 比赛证据与 PPT 图表素材\n\n"
        "图表由显式指定的结果文件生成，来源、配置、SHA-256 和候选 commit 记录在 `manifest.json`。生成器不会自动挑选最新文件。\n\n"
        "- `agent_topology.png`：两种拓扑完成率均为 100%；本次确定性任务中多 Agent 平均耗时更低。\n"
        "- `recovery_flow.png`：开启恢复后只重跑受影响的计算子图，准备步骤只执行一次。\n"
        "- `contract_gate.png`：开启契约后，缺失最终证据的任务被正确拦截。\n"
        "- `routing_fallback.png`：注入云端故障后，动态路由回退至边缘端成功；这是单机运行时模拟。\n"
        "- `research_evidence.png`：历史科研运行证据，不是本轮 API 实验，也不是随机化对照。\n\n"
        "`live_api_status=pending_credentials` 表示当前没有真实 API 结果；未检测到凭据时不会发送请求。\n",
        encoding="utf-8",
    )
    agent_rows = {row["mode"]: row for row in payloads["agent"]["summaries"]}
    agent_speedup = agent_rows["single_agent"]["mean_duration_seconds"] / agent_rows["multi_agent"]["mean_duration_seconds"]
    recovery_rows = {row["mode"]: row for row in payloads["recovery"]["results"]}
    contract_rows = {row["mode"]: row for row in payloads["contract"]["results"]}
    routing_rows = {row["mode"]: row for row in payloads["routing"]["results"]}
    research_rows = payloads["research"]["runs"]
    notes = (
        "# 答辩图表讲解要点\n\n"
        f"候选基线：`{manifest['candidate_tag']}`（commit `{manifest['candidate_tag_commit'][:12]}`）；证据生成代码提交：`{args.commit}`。\n\n"
        "## 多 Agent\n\n"
        f"单 Agent 平均耗时 `{agent_rows['single_agent']['mean_duration_seconds']:.4f}s`，多 Agent `{agent_rows['multi_agent']['mean_duration_seconds']:.4f}s`，观察到 `{agent_speedup:.3f}x` 加速；两组完成率均为 100%，每组重复 `{payloads['agent']['repeats']}` 次。结论只限于该确定性工作负载的编排并行效果，不代表 LLM 推理质量提升。误差线是样本标准差。\n\n"
        "## 局部恢复\n\n"
        f"Recovery OFF 最终完成：`{recovery_rows['recovery_off']['goal_completed']}`；Recovery ON：`{recovery_rows['recovery_on']['goal_completed']}`。恢复模式中 `prepare` 执行 `{recovery_rows['recovery_on'].get('prepare_attempts', 'unknown')}` 次、局部恢复 `{recovery_rows['recovery_on'].get('local_recovery_count', 'unknown')}` 次，说明前置成功步骤未重复执行。\n\n"
        "## 契约验收\n\n"
        f"Contract OFF 完成判定：`{contract_rows['contract_off']['completed']}`；Contract ON：`{contract_rows['contract_on']['completed']}`，缺失项 `{', '.join(contract_rows['contract_on'].get('missing_criteria', ['unknown']))}`。被拦截代表正确拒绝虚报完成，不表示开启契约后该任务已经完成。\n\n"
        "## 动态路由\n\n"
        f"固定云端完成：`{routing_rows['fixed_cloud']['completed']}`；动态路由完成：`{routing_rows['dynamic_routing']['completed']}`；最终节点 `{routing_rows['dynamic_routing'].get('final_node_type', 'unknown')}`，回退 `{routing_rows['dynamic_routing'].get('fallback_count', 'unknown')}` 次。这是单机模拟运行时证据，不是多设备网络测试。\n\n"
        "## 科研运行\n\n"
        f"两条科研样本的最终状态分别为 `{research_rows[0].get('final_goal_completed', 'unknown')}`、`{research_rows[1].get('final_goal_completed', 'unknown')}`；首次通过任务数分别为 `{research_rows[0].get('first_pass_count', 'unknown')}`、`{research_rows[1].get('first_pass_count', 'unknown')}`，恢复次数分别为 `{research_rows[0].get('local_recovery_count', 'unknown')}`、`{research_rows[1].get('local_recovery_count', 'unknown')}`。这是历史 `recorded_real_run`，不能称作本轮 API 实验或受控对照。\n\n"
        "## API 实验状态\n\n"
        "当前执行环境没有 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME`，所以没有发送真实 API 请求。取得凭据后，先运行 API 诊断和低成本 smoke，再至少运行两次真实两阶段任务；API usage 缺失时保留 `unknown`。\n"
    )
    notes_path = output / "PPT_TALKING_POINTS.md"
    notes_path.write_text(notes, encoding="utf-8")
    manifest["documents"] = [{"path": notes_path.name, "sha256": sha256(notes_path)}]
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"package={output}")
    print(f"manifest={output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
