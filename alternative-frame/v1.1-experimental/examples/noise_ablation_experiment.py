"""Noise ablation experiment: bounded message bus vs unbounded broadcast baseline.

消融实验（对照实验）设计：
- ON  组：使用 core.experimental.coordination.BoundedMessageBus
  （邻居拓扑限制 + TTL 过期 + 跳数上限 + 重复去重）——即项目的降噪机制。
- OFF 组：UnboundedBus 对照基线（仅为本实验编写，不并入 core）：
  收到消息后广播给所有其他智能体、无 TTL、无去重、无跳数限制，
  且回复引用完整原文，模拟上下文滚雪球导致的 Token 冗余爆炸。

两组跑完全相同的确定性工作负载（无 API 调用、可复现），
对比：消息条数、送达条数、估算 Token、任务完成情况、耗时。

运行：python examples/noise_ablation_experiment.py
输出：打印对比表格，并把 JSON 报告写入 reports/noise-ablation/。
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 支持直接 python examples/xxx.py 运行

from core.experimental.coordination import BoundedMessageBus

# ---------------- 可调参数 ----------------
AGENTS = ["coordinator", "planner", "coder", "tester", "reviewer"]
INITIATOR = "coordinator"
FINAL_DECIDER = "coordinator"      # 收到 review_result 才算任务完成
MAX_ROUNDS = 30                    # 轮数上限，防止无界组无限膨胀
REPEATS = 5                        # 与既有 1.248x 实验保持一致：5 次重复
TOKEN_CHARS_PER_TOKEN = 2.0        # 估算：约 2 字符 = 1 token（粗估，注明即可）


# ---------------- 对照基线：无界广播总线 ----------------
class UnboundedBus:
    """OFF 组专用对照基线：广播、无 TTL、无去重、无跳数限制。

    注意：这是故意"不做降噪"的反面教材，仅用于实验对照，不并入 core。
    """

    def __init__(self, agents: list[str]):
        self.agents = list(agents)
        self._mailboxes: dict[str, list[dict]] = {a: [] for a in agents}
        self.sent = 0

    def send(self, sender: str, payload: dict) -> None:
        for recipient in self.agents:
            if recipient != sender:
                self._mailboxes[recipient].append(dict(payload))
                self.sent += 1

    def receive(self, agent: str) -> list[dict]:
        msgs = self._mailboxes[agent]
        self._mailboxes[agent] = []
        return msgs


# ---------------- 确定性工作负载 ----------------
@dataclass
class RunResult:
    messages_sent: int = 0
    messages_delivered: int = 0
    dropped_or_ignored: int = 0
    estimated_tokens: float = 0.0
    completed: bool = False
    wall_seconds: float = 0.0
    rounds_used: int = 0

    def as_dict(self) -> dict:
        return {
            "messages_sent": self.messages_sent,
            "messages_delivered": self.messages_delivered,
            "dropped_or_ignored": self.dropped_or_ignored,
            "estimated_tokens": round(self.estimated_tokens, 1),
            "completed": self.completed,
            "wall_seconds": round(self.wall_seconds, 6),
            "rounds_used": self.rounds_used,
        }


def estimate_tokens(payload: dict) -> float:
    return len(json.dumps(payload, ensure_ascii=False)) / TOKEN_CHARS_PER_TOKEN


def run_bounded() -> RunResult:
    """ON 组：降噪机制全开。拓扑为单向流水线环，回复只发给下游邻居。"""
    result = RunResult()
    # 流水线环：coordinator -> planner -> coder -> tester -> reviewer -> coordinator
    topology = {
        "coordinator": {"planner", "reviewer"},
        "planner": {"coder"},
        "coder": {"tester"},
        "tester": {"reviewer"},
        "reviewer": {"coordinator"},
    }
    bus = BoundedMessageBus(topology, max_hops=6, max_ttl_seconds=300)
    t0 = time.perf_counter()

    bus.send(INITIATOR, "planner", {"kind": "review_request", "task_id": "T1"})
    result.messages_sent += 1

    completed = False
    round_no = 0
    while round_no < MAX_ROUNDS and not completed:
        round_no += 1
        any_activity = False
        for agent in AGENTS:
            received = bus.receive(agent)
            fresh = [m for m in received]
            result.messages_delivered += len(fresh)
            # 送达即计 Token（收到的内容都要进上下文）
            result.estimated_tokens += sum(estimate_tokens(m.payload) for m in fresh)
            for msg in fresh:
                any_activity = True
                kind = msg.payload.get("kind")
                if agent == FINAL_DECIDER and kind == "review_result":
                    completed = True
                    continue
                # 确定性转发策略：沿流水线下游传递，回复引用原文（上下文累积）
                targets = {
                    "coordinator": ["planner"],
                    "planner": ["coder"],
                    "coder": ["tester"],
                    "tester": ["reviewer"],
                    "reviewer": ["coordinator"],
                }[agent]
                for target in targets:
                    payload = {
                        "kind": "review_result" if agent == "reviewer" else kind,
                        "task_id": msg.payload.get("task_id"),
                        "quote": msg.payload,          # 引用原文：上下文累积
                        "processed_by": agent,
                    }
                    bus.send(agent, target, payload)
                    result.messages_sent += 1
        if not any_activity:
            break
    result.completed = completed
    result.rounds_used = round_no
    result.wall_seconds = time.perf_counter() - t0
    return result


def run_unbounded() -> RunResult:
    """OFF 组：无降噪基线。每人收到就广播给所有人，回复引用完整原文。"""
    result = RunResult()
    bus = UnboundedBus(AGENTS)
    t0 = time.perf_counter()

    bus.send(INITIATOR, {"kind": "review_request", "task_id": "T1"})
    result.messages_sent += 1

    completed = False
    round_no = 0
    while round_no < MAX_ROUNDS and not completed:
        round_no += 1
        any_activity = False
        for agent in AGENTS:
            received = bus.receive(agent)
            result.messages_delivered += len(received)
            result.estimated_tokens += sum(estimate_tokens(m) for m in received)
            for msg in received:
                any_activity = True
                kind = msg.get("kind")
                if agent == FINAL_DECIDER and kind == "review_result":
                    completed = True
                    continue
                payload = {
                    "kind": "review_result" if agent == "reviewer" else kind,
                    "task_id": msg.get("task_id"),
                    "quote": msg,                      # 层层引用：上下文滚雪球
                    "processed_by": agent,
                }
                bus.send(agent, payload)               # 广播给所有其他人
                result.messages_sent += 1
        if not any_activity:
            break
    result.completed = completed
    result.rounds_used = round_no
    result.wall_seconds = time.perf_counter() - t0
    return result


def summarize(runs: list[RunResult]) -> dict:
    def mean(key: str) -> float:
        return statistics.fmean(getattr(r, key) for r in runs)

    return {
        "messages_sent_mean": round(mean("messages_sent"), 1),
        "messages_delivered_mean": round(mean("messages_delivered"), 1),
        "estimated_tokens_mean": round(mean("estimated_tokens"), 1),
        "completed_all": all(r.completed for r in runs),
        "wall_seconds_mean": round(mean("wall_seconds"), 6),
        "repeats": len(runs),
    }


def main() -> None:
    on_runs = [run_bounded() for _ in range(REPEATS)]
    off_runs = [run_unbounded() for _ in range(REPEATS)]

    summary = {
        "experiment": "noise_ablation_bounded_vs_unbounded",
        "workload": "deterministic 5-agent review pipeline, no LLM calls",
        "params": {
            "agents": AGENTS,
            "max_rounds": MAX_ROUNDS,
            "repeats": REPEATS,
            "token_estimate": "chars/2, rough",
        },
        "bounded_on": summarize(on_runs),
        "unbounded_off": summarize(off_runs),
        "noise_reduction": {
            "messages_ratio": round(
                summarize(off_runs)["messages_delivered_mean"]
                / max(summarize(on_runs)["messages_delivered_mean"], 1), 2),
            "token_ratio": round(
                summarize(off_runs)["estimated_tokens_mean"]
                / max(summarize(on_runs)["estimated_tokens_mean"], 1), 2),
        },
        "honesty_boundary": [
            "确定性模拟工作负载，不含真实 LLM 调用",
            "结论仅限于该工作负载下的通信开销对比，不代表推理质量",
        ],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    out_dir = Path(__file__).resolve().parent.parent / "reports" / "noise-ablation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"noise-ablation-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 降噪消融实验结果（重复 %d 次，均值） ===" % REPEATS)
    for key in ["messages_sent_mean", "messages_delivered_mean",
                "estimated_tokens_mean", "completed_all", "wall_seconds_mean"]:
        print(f"{key:>24}: ON={summary['bounded_on'][key]}  OFF={summary['unbounded_off'][key]}")
    print(f"{'消息量降噪倍数':>18}: {summary['noise_reduction']['messages_ratio']}x")
    print(f"{'Token 降噪倍数':>18}: {summary['noise_reduction']['token_ratio']}x")
    print("报告已写入:", out_path)


if __name__ == "__main__":
    main()
