"""Three-phase proof that Replan and resume still pass through NodeRouter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from core.agents import Agent, AgentRegistry
from core.long_horizon import GoalEvaluation, LongHorizonController, LongHorizonStore
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator
from core.runtime_nodes import (
    CloudNode,
    DeviceNode,
    EdgeNode,
    LongHorizonEventSink,
    NodeRoutedAgent,
    NodeStateStore,
    RuntimeExecutor,
    build_runtime_view,
)


GOAL = "验证跨阶段 Replan、暂停恢复和端边云动态路由一致性"


class PhaseAgent(Agent):
    role = "researcher"

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        return AgentResult(
            task.id,
            "success",
            summary=f"{task.id} executed on {task.metadata['node_id']}",
            evidence=[f"phase_task={task.id}"],
        )


class ThreePhaseEvaluator:
    def evaluate(self, state, plan, report):
        completed = state.phase >= 2 and report.status == "success"
        return GoalEvaluation(
            completed,
            "three routed phases completed" if completed else "continue to next routed phase",
            next_focus=[] if completed else ["execute next Replan task through NodeRouter"],
        )


def _task(task_id: str, preferred_tier: str, capability: str, privacy: str = "public") -> SubTask:
    return SubTask(
        task_id,
        "researcher",
        f"execute {task_id}",
        max_retries=0,
        metadata={
            "privacy_level": privacy,
            "required_capabilities": [capability],
            "preferred_tier": preferred_tier,
        },
    )


def _initial_plan(_state) -> Plan:
    return Plan(GOAL, [_task("phase1_device_preprocess", "device", "preprocess", "sensitive")])


def _replan(state, _evaluation) -> Plan:
    if state.phase == 1:
        return Plan(GOAL, [_task("phase2_cloud_recovery", "cloud", "compute")])
    return Plan(GOAL, [_task("phase3_post_resume", "cloud", "compute")])


def _fresh_nodes() -> list:
    return [
        DeviceNode("device-1", {"preprocess"}),
        EdgeNode("edge-1", {"compute"}, estimated_latency_ms=20),
        CloudNode("cloud-1", {"compute"}, estimated_latency_ms=60),
    ]


def _controller(store: LongHorizonStore, run_id: str, nodes: list, pause_after_phase_two: bool):
    node_state_store = NodeStateStore(store.run_dir(run_id) / "node_state.json")

    def node_provider(task: SubTask):
        cloud = next(node for node in nodes if node.node_type == "cloud")
        if task.id == "phase2_cloud_recovery" and cloud.online:
            cloud.execution_failure_mode = "offline"
        else:
            cloud.execution_failure_mode = None
        return nodes

    registry = AgentRegistry()
    registry.register(
        NodeRoutedAgent(
            PhaseAgent(),
            node_provider,
            RuntimeExecutor(on_event=LongHorizonEventSink(store, run_id)),
            node_state_store=node_state_store,
        )
    )
    controller = None

    def on_event(event, payload):
        if pause_after_phase_two and event == "phase_finished" and payload.get("phase") == 2:
            controller.request_pause()

    controller = LongHorizonController(
        Orchestrator(registry, max_workers=1),
        _initial_plan,
        store,
        evaluator=ThreePhaseEvaluator(),
        replanner=_replan,
        max_phases=3,
        max_total_tasks=3,
        on_event=on_event,
    )
    return controller


def run_demo(root: Path, run_id: str):
    store = LongHorizonStore(root)
    first_nodes = _fresh_nodes()
    paused = _controller(store, run_id, first_nodes, True).run(GOAL, run_id=run_id)
    if paused.status != "paused" or paused.state.phase != 2:
        raise RuntimeError("demo did not pause after the second phase")

    resumed_nodes = _fresh_nodes()
    completed = _controller(store, run_id, resumed_nodes, False).run(GOAL, run_id=run_id, resume=True)
    events_path = store.run_dir(run_id) / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    view = build_runtime_view(
        resumed_nodes, completed.state.evidence_records, events, run_id=run_id
    ).to_dict()
    (store.run_dir(run_id) / "runtime_view.json").write_text(
        json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paused, completed, view, store.run_dir(run_id)


def main() -> None:
    root = Path(__file__).resolve().parent / "runs" / "edge_cloud_replan"
    paused, completed, view, run_dir = run_demo(root, "replan_" + uuid4().hex[:8])
    print(f"paused_phase={paused.state.phase} final_status={completed.status}")
    print(f"run_dir={run_dir}")
    print(json.dumps(view["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
