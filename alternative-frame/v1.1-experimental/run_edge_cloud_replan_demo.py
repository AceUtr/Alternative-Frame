"""Final freeze proof: contract-driven Replan plus current node probing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from core.agents import Agent, AgentRegistry
from core.long_horizon import (
    AcceptanceContract,
    GoalCriterion,
    GoalEvaluation,
    LongHorizonController,
    LongHorizonStore,
)
from core.long_horizon.evidence import EvidenceBundle, HardEvidenceGate
from core.models import AgentResult, Plan, SubTask, utc_now
from core.orchestrator import Orchestrator
from core.runtime_nodes import (
    CloudNode,
    DeviceNode,
    EdgeNode,
    LongHorizonEventSink,
    NodeProbeResult,
    NodeRoutedAgent,
    NodeStateStore,
    RuntimeExecutor,
    build_runtime_view,
)
from core.tools import FileEditor


GOAL = "完成合同驱动的端边云实验、故障回退、恢复任务和最终报告"
DEVICE_CRITERION = "device_sensitive_preprocess"
EXPERIMENT_CRITERION = "high_compute_artifact"
FALLBACK_CRITERION = "cloud_edge_fallback_evidence"
RECOVERY_CRITERION = "post_resume_task_completed"
REPORT_CRITERION = "final_report_exists"


def build_contract() -> AcceptanceContract:
    return AcceptanceContract(
        GOAL,
        [
            GoalCriterion(DEVICE_CRITERION, "sensitive preprocessing completed on device", "runtime_route"),
            GoalCriterion(EXPERIMENT_CRITERION, "high-compute experiment artifact exists", "file_exists", path="artifacts/cloud_experiment.json"),
            GoalCriterion(FALLBACK_CRITERION, "cloud failure and edge fallback are evidenced", "runtime_fallback"),
            GoalCriterion(RECOVERY_CRITERION, "post-resume routed task completed", "runtime_route"),
            GoalCriterion(REPORT_CRITERION, "final report exists", "file_exists", path="artifacts/final_report.json"),
        ],
        goal_summary="All required edge-cloud evidence is produced by the current run.",
        constraints=["Replan maps missing_criteria to routed tasks", "Historical node snapshots are audit-only"],
    )


class ContractArtifactAgent(Agent):
    role = "researcher"

    def __init__(self, workspace: Path) -> None:
        self.editor = FileEditor(workspace)

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        started = utc_now()
        output_path = task.metadata.get("output_path")
        if not output_path:
            return AgentResult(task.id, "success", summary=f"{task.id} completed")
        payload = {
            "task_id": task.id,
            "node_id": task.metadata["node_id"],
            "node_type": task.metadata["deployment_target"],
            "dependencies": sorted(context),
        }
        arguments = {
            "action": "write",
            "path": output_path,
            "content": json.dumps(payload, ensure_ascii=False, indent=2),
        }
        result = self.editor.execute(arguments)
        record = {
            "tool": result.tool,
            "arguments": arguments,
            "success": result.success,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "metadata": dict(result.metadata),
            "output_excerpt": result.output,
            "error": result.error,
        }
        return AgentResult(
            task.id,
            "success" if result.success else "failed",
            summary=f"{task.id} artifact generated on {task.metadata['node_id']}",
            artifacts=[output_path] if result.success else [],
            evidence=[f"artifact={output_path}"] if result.success else [],
            tool_records=[record],
            failures=[] if result.success else [result.error],
            started_at=started,
            finished_at=utc_now(),
        )


class EdgeCloudContractEvaluator:
    """Deterministic contract evaluator scoped to the edge-cloud demo."""

    def __init__(self, contract: AcceptanceContract, workspace: Path) -> None:
        self.contract = contract
        self.file_gate = HardEvidenceGate(workspace)

    def evaluate(self, state, plan, report) -> GoalEvaluation:
        bundle = EvidenceBundle.collect(state, report)
        runtime = [row for row in bundle.tool_records if row.get("tool") == "runtime_executor"]
        file_contract = AcceptanceContract(
            self.contract.goal,
            [criterion for criterion in self.contract.criteria if criterion.check_type == "file_exists"],
        )
        file_results = {row.criterion_id: row for row in self.file_gate.evaluate(file_contract, bundle).results}
        passed = []
        evidence = []

        device_rows = [
            row for row in runtime
            if row.get("task_id") == "device_sensitive_preprocess"
            and row.get("success") is True
            and row.get("node_type") == "device"
        ]
        if device_rows:
            passed.append(DEVICE_CRITERION)
            evidence.append("device_sensitive_preprocess: runtime_executor node_type=device")

        for criterion_id in (EXPERIMENT_CRITERION, REPORT_CRITERION):
            result = file_results[criterion_id]
            if result.status == "passed":
                passed.append(criterion_id)
                evidence.extend(f"{criterion_id}: {item}" for item in result.evidence)

        fallback_rows = [row for row in runtime if row.get("task_id") == "cloud_edge_fallback"]
        if (
            any(row.get("node_type") == "cloud" and row.get("success") is False for row in fallback_rows)
            and any(
                row.get("node_type") == "edge"
                and row.get("success") is True
                and int(row.get("fallback_count") or 0) >= 1
                for row in fallback_rows
            )
        ):
            passed.append(FALLBACK_CRITERION)
            evidence.append("cloud_edge_fallback_evidence: failed cloud attempt followed by successful edge attempt")

        if any(
            row.get("task_id") == "post_resume_task"
            and row.get("success") is True
            for row in runtime
        ):
            passed.append(RECOVERY_CRITERION)
            evidence.append("post_resume_task_completed: runtime_executor success")

        required = [criterion.id for criterion in self.contract.criteria if criterion.required]
        missing = [criterion_id for criterion_id in required if criterion_id not in passed]
        return GoalEvaluation(
            completed=not missing and report.status == "success",
            reason="all required contract evidence passed" if not missing else "required contract evidence is missing",
            satisfied_criteria=passed,
            missing_criteria=missing,
            failures=[] if report.status == "success" else list(report.failures),
            next_focus=[f"satisfy contract criterion: {item}" for item in missing],
            evidence=evidence,
        )


def _task(task_id: str, preferred_tier: str, capability: str, output_path: str, privacy="public", depends_on=None) -> SubTask:
    return SubTask(
        task_id,
        "researcher",
        f"satisfy contract evidence for {task_id}",
        depends_on=list(depends_on or []),
        max_retries=0,
        metadata={
            "privacy_level": privacy,
            "required_capabilities": [capability],
            "preferred_tier": preferred_tier,
            "output_path": output_path,
            "expected_outputs": [output_path],
        },
    )


def initial_plan(_state) -> Plan:
    return Plan(
        GOAL,
        [_task("device_sensitive_preprocess", "device", "preprocess", "artifacts/preprocessed.json", "sensitive")],
    )


def contract_replan(_state, evaluation: GoalEvaluation) -> Plan:
    """Map contract gaps to tasks without consulting a phase number."""
    missing = set(evaluation.missing_criteria)
    tasks = []
    if EXPERIMENT_CRITERION in missing or FALLBACK_CRITERION in missing:
        tasks.append(_task("cloud_edge_fallback", "cloud", "compute", "artifacts/cloud_experiment.json"))
        return Plan(GOAL, tasks)
    if RECOVERY_CRITERION in missing:
        tasks.append(_task("post_resume_task", "cloud", "compute", "artifacts/post_resume.json"))
    if REPORT_CRITERION in missing:
        dependencies = [task.id for task in tasks]
        tasks.append(_task("final_report", "edge", "report", "artifacts/final_report.json", depends_on=dependencies))
    if not tasks:
        raise ValueError(f"no task mapping for missing criteria: {sorted(missing)}")
    return Plan(GOAL, tasks)


def fresh_nodes() -> list:
    return [
        DeviceNode("device-1", {"preprocess"}),
        EdgeNode("edge-1", {"compute", "report"}, estimated_latency_ms=20),
        CloudNode("cloud-1", {"compute"}, estimated_latency_ms=60),
    ]


def build_controller(store, run_id, workspace, nodes, probe, pause_after_phase_two):
    event_sink = LongHorizonEventSink(store, run_id)
    state_store = NodeStateStore(
        store.run_dir(run_id) / "node_state.json",
        run_id=run_id,
        probe=probe,
        on_event=event_sink,
    )

    def node_provider(task):
        cloud = next(node for node in nodes if node.node_type == "cloud")
        cloud.execution_failure_mode = "offline" if task.id == "cloud_edge_fallback" else None
        return nodes

    registry = AgentRegistry()
    registry.register(
        NodeRoutedAgent(
            ContractArtifactAgent(workspace),
            node_provider,
            RuntimeExecutor(on_event=event_sink),
            node_state_store=state_store,
        )
    )
    controller = None

    def on_event(event, payload):
        if pause_after_phase_two and event == "phase_finished" and payload.get("phase") == 2:
            controller.request_pause()

    contract = build_contract()
    controller = LongHorizonController(
        Orchestrator(registry, max_workers=1),
        initial_plan,
        store,
        evaluator=EdgeCloudContractEvaluator(contract, workspace),
        replanner=contract_replan,
        max_phases=3,
        max_total_tasks=5,
        on_event=on_event,
        acceptance_contract=contract.to_dict(),
    )
    return controller


def run_demo(
    root: Path,
    run_id: str,
    resume_cloud_online: bool = True,
    preseed_stale_artifacts: bool = False,
):
    store = LongHorizonStore(root)
    workspace = store.run_dir(run_id) / "workspace"
    workspace.mkdir(parents=True, exist_ok=False)
    if preseed_stale_artifacts:
        artifacts = workspace / "artifacts"
        artifacts.mkdir()
        for name in ("cloud_experiment.json", "final_report.json"):
            (artifacts / name).write_text('{"stale": true}', encoding="utf-8")
    first_nodes = fresh_nodes()
    current_probe = lambda node: NodeProbeResult(node.online, node.network_available)
    paused = build_controller(store, run_id, workspace, first_nodes, current_probe, True).run(GOAL, run_id=run_id)
    if paused.status != "paused" or paused.state.phase != 2:
        raise RuntimeError("demo did not pause after contract-driven phase two")

    resumed_nodes = fresh_nodes()
    resume_probe = lambda node: NodeProbeResult(
        resume_cloud_online if node.node_type == "cloud" else True,
        True,
    )
    completed = build_controller(store, run_id, workspace, resumed_nodes, resume_probe, False).run(
        GOAL, run_id=run_id, resume=True
    )
    events_path = store.run_dir(run_id) / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    view = build_runtime_view(resumed_nodes, completed.state.evidence_records, events, run_id=run_id).to_dict()
    (store.run_dir(run_id) / "runtime_view.json").write_text(
        json.dumps(view, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paused, completed, view, store.run_dir(run_id)


def main() -> None:
    root = Path(__file__).resolve().parent / "runs" / "edge_cloud_replan"
    paused, completed, view, run_dir = run_demo(root, "replan_" + uuid4().hex[:8])
    print(f"phase1_missing={paused.state.phases[0].evaluation['missing_criteria']}")
    print(f"paused_phase={paused.state.phase} final_status={completed.status}")
    print(f"run_dir={run_dir}")
    print(json.dumps(view["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
