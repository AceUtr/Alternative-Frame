"""A deterministic research workflow routed across simulated device/edge/cloud nodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from core.agents import Agent, AgentRegistry
from core.long_horizon import (
    AcceptanceContract,
    DeterministicGlobalEvaluator,
    GoalCriterion,
    LongHorizonController,
    LongHorizonStore,
)
from core.models import AgentResult, Plan, SubTask, utc_now
from core.orchestrator import Orchestrator
from core.runtime_nodes import (
    CloudNode,
    DeviceNode,
    EdgeNode,
    LongHorizonEventSink,
    NodeRoutedAgent,
    RuntimeExecutor,
    build_runtime_view,
)
from core.tools import FileEditor


GOAL = "完成一个带敏感数据预处理、边缘推理、云端实验和故障回退的科研任务链"


@dataclass
class DemoRun:
    report: Any
    run_dir: Path
    workspace: Path
    nodes: list
    runtime_view: dict


class ResearchWorkflowAgent(Agent):
    """Perform small but real file-backed research transformations."""

    role = "researcher"

    def __init__(self, workspace: Path) -> None:
        self.editor = FileEditor(workspace)

    @staticmethod
    def _tool_record(result, arguments: dict) -> dict:
        return {
            "tool": result.tool,
            "arguments": dict(arguments),
            "success": result.success,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "metadata": dict(result.metadata),
            "output_excerpt": str(result.output)[:500],
            "error": result.error,
        }

    def _read_json(self, path: str, records: list[dict]) -> Any:
        arguments = {"action": "read", "path": path}
        result = self.editor.execute(arguments)
        records.append(self._tool_record(result, arguments))
        if not result.success:
            raise RuntimeError(result.error)
        return json.loads(result.output)

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        started = utc_now()
        records: list[dict] = []
        output_path = str(task.metadata["output_path"])
        node_type = str(task.metadata.get("deployment_target", "unknown"))
        try:
            if task.id == "preprocess_sensitive":
                raw = self._read_json("inputs/sensitive_measurements.json", records)
                payload = {
                    "sample_count": len(raw),
                    "normalized_values": [round(float(row["value"]) / 100.0, 3) for row in raw],
                    "identifiers_removed": True,
                    "processed_on": node_type,
                }
            elif task.id == "edge_inference":
                prepared = self._read_json("artifacts/preprocessed.json", records)
                values = prepared["normalized_values"]
                payload = {
                    "prediction": "stable" if sum(values) / len(values) < 0.8 else "review",
                    "confidence": 0.91,
                    "inferred_on": node_type,
                }
            elif task.id == "cloud_experiment":
                inference = self._read_json("artifacts/edge_inference.json", records)
                payload = {
                    "experiment": "parameter_sweep",
                    "candidate_scores": [0.82, 0.89, 0.93],
                    "best_score": 0.93,
                    "upstream_prediction": inference["prediction"],
                    "executed_on": node_type,
                }
            elif task.id == "cloud_fault_recovery":
                experiment = self._read_json("artifacts/cloud_experiment.json", records)
                payload = {
                    "recovered": True,
                    "best_score": experiment["best_score"],
                    "fallback_node_type": node_type,
                }
            else:
                raise ValueError(f"unsupported research task: {task.id}")

            arguments = {
                "action": "write",
                "path": output_path,
                "content": json.dumps(payload, ensure_ascii=False, indent=2),
            }
            write_result = self.editor.execute(arguments)
            records.append(self._tool_record(write_result, arguments))
            if not write_result.success:
                raise RuntimeError(write_result.error)
            return AgentResult(
                task.id,
                "success",
                summary=f"{task.id} completed on {node_type}",
                artifacts=[output_path],
                evidence=[f"output={output_path}", f"node_type={node_type}"],
                tool_records=records,
                started_at=started,
                finished_at=utc_now(),
            )
        except Exception as exc:
            return AgentResult(
                task.id,
                "failed",
                summary=f"{task.id} failed",
                tool_records=records,
                failures=[f"{type(exc).__name__}: {exc}"],
                started_at=started,
                finished_at=utc_now(),
            )


def build_plan() -> Plan:
    shared_check = [{"id": "output", "check_type": "file_exists"}]
    return Plan(
        GOAL,
        [
            SubTask(
                "preprocess_sensitive",
                "researcher",
                "remove identifiers and normalize sensitive measurements locally",
                max_retries=0,
                metadata={
                    "privacy_level": "sensitive",
                    "required_capabilities": ["data_preprocess"],
                    "preferred_tier": "device",
                    "output_path": "artifacts/preprocessed.json",
                    "expected_outputs": ["artifacts/preprocessed.json"],
                    "checks": shared_check,
                },
            ),
            SubTask(
                "edge_inference",
                "researcher",
                "run ordinary inference on anonymized data",
                depends_on=["preprocess_sensitive"],
                max_retries=0,
                metadata={
                    "required_capabilities": ["inference"],
                    "preferred_tier": "edge",
                    "output_path": "artifacts/edge_inference.json",
                    "expected_outputs": ["artifacts/edge_inference.json"],
                    "checks": shared_check,
                },
            ),
            SubTask(
                "cloud_experiment",
                "researcher",
                "run a high-compute parameter sweep",
                depends_on=["edge_inference"],
                max_retries=0,
                metadata={
                    "network_required": True,
                    "required_capabilities": ["high_compute"],
                    "preferred_tier": "cloud",
                    "output_path": "artifacts/cloud_experiment.json",
                    "expected_outputs": ["artifacts/cloud_experiment.json"],
                    "checks": shared_check,
                },
            ),
            SubTask(
                "cloud_fault_recovery",
                "researcher",
                "continue the high-compute experiment while the cloud node fails",
                depends_on=["cloud_experiment"],
                max_retries=0,
                metadata={
                    "network_required": True,
                    "required_capabilities": ["high_compute"],
                    "preferred_tier": "cloud",
                    "output_path": "artifacts/recovered_experiment.json",
                    "expected_outputs": ["artifacts/recovered_experiment.json"],
                    "checks": shared_check,
                },
            ),
        ],
    )


def build_nodes() -> list:
    return [
        DeviceNode("device-lab-1", {"data_preprocess"}, estimated_latency_ms=5),
        EdgeNode("edge-lab-1", {"inference", "high_compute"}, estimated_latency_ms=18),
        CloudNode("cloud-lab-1", {"inference", "high_compute"}, estimated_latency_ms=60),
    ]


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_demo(root: Path, run_id: str) -> DemoRun:
    store = LongHorizonStore(root)
    run_dir = store.run_dir(run_id)
    workspace = run_dir / "workspace"
    (workspace / "inputs").mkdir(parents=True, exist_ok=False)
    (workspace / "inputs" / "sensitive_measurements.json").write_text(
        json.dumps(
            [
                {"participant_id": "P-001", "value": 64},
                {"participant_id": "P-002", "value": 72},
                {"participant_id": "P-003", "value": 81},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    plan = build_plan()
    contract = AcceptanceContract.from_plan(GOAL, plan)
    nodes = build_nodes()

    def node_provider(task: SubTask):
        cloud = next(node for node in nodes if node.node_type == "cloud")
        cloud.execution_failure_mode = "offline" if task.id == "cloud_fault_recovery" else None
        return nodes

    registry = AgentRegistry()
    registry.register(
        NodeRoutedAgent(
            ResearchWorkflowAgent(workspace),
            node_provider,
            RuntimeExecutor(on_event=LongHorizonEventSink(store, run_id)),
        )
    )
    controller = LongHorizonController(
        Orchestrator(registry, max_workers=1),
        lambda _state: plan,
        store,
        evaluator=DeterministicGlobalEvaluator(contract, workspace),
        max_phases=1,
        max_total_tasks=4,
        acceptance_contract=contract.to_dict(),
    )
    report = controller.run(GOAL, run_id=run_id)
    events = _read_events(run_dir / "events.jsonl")
    runtime_view = build_runtime_view(
        nodes, report.state.evidence_records, events, run_id=run_id
    ).to_dict()
    (run_dir / "runtime_view.json").write_text(
        json.dumps(runtime_view, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return DemoRun(report, run_dir, workspace, nodes, runtime_view)


def main() -> None:
    root = Path(__file__).resolve().parent / "runs" / "edge_cloud_long_horizon"
    result = run_demo(root, "research_" + uuid4().hex[:8])
    state = result.report.state
    if state.status != "completed":
        raise RuntimeError(f"demo did not complete: {state.last_error}")
    print(f"run_id={state.run_id} status={state.status} phases={state.phase}")
    print(f"state={result.run_dir / 'state.json'}")
    print(f"events={result.run_dir / 'events.jsonl'}")
    print(f"ui_data={result.run_dir / 'runtime_view.json'}")
    print(json.dumps(result.runtime_view["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
