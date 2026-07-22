"""Run a reproducible real-model two-phase long-horizon demonstration.

Required environment variables: MODEL_BASE_URL, MODEL_API_KEY, MODEL_NAME.
The key is read only from process memory and is never persisted.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from core.agents import Agent, AgentRegistry
from core.long_horizon import (
    AcceptanceContract,
    ContractAwarePlanner,
    GoalCriterion,
    LongHorizonController,
    LongHorizonStore,
    StructuredGlobalEvaluator,
    StructuredReplanner,
)
from core.model_client import ModelConfig, OpenAICompatibleClient
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator
from core.tool_calling_agent import ToolCallingAgent
from core.tools import FileEditor, GitClient, ShellRunner, TestRunner, ToolRegistry


GOAL = "实现一个可测试的加法计算器，通过自动化测试，并提供 FINAL_EVIDENCE.md 最终验证报告"


class AuditThenDelegate(Agent):
    """Make phase-one omission deterministic while delegating recovery to the real model."""

    role = "reviewer"

    def __init__(self, delegate):
        self.delegate = delegate

    def run(self, task, context):
        if task.id == "audit_final_evidence":
            return AgentResult(
                task.id,
                "success",
                summary="Independent audit: FINAL_EVIDENCE.md is missing; intentionally did not repair it.",
            )
        return self.delegate.run(task, context)


def build_registry(client, workspace):
    registry = AgentRegistry()
    shell = ShellRunner(workspace)
    editor = FileEditor(workspace)
    tests = TestRunner(shell)
    git = GitClient(workspace)
    role_tools = {
        "developer": [editor, shell, tests, git],
        "tester": [editor, shell, tests],
        "reviewer": [editor, tests, git],
        "analyst": [editor],
        "architect": [editor],
        "researcher": [editor],
        "experimenter": [editor, shell],
    }
    for role, tools in role_tools.items():
        agent = ToolCallingAgent(
            role,
            client,
            ToolRegistry(tools),
            "Complete the assigned task with real workspace tools and preserve concise verification evidence.",
            max_steps=16,
        )
        registry.register(AuditThenDelegate(agent) if role == "reviewer" else agent)
    return registry


def main():
    client = OpenAICompatibleClient(ModelConfig.from_env())
    run_id = "real_two_phase_" + uuid4().hex[:8]
    demo_root = Path(__file__).resolve().parent / "runs" / "real_two_phase"
    workspace = demo_root / run_id / "workspace"
    workspace.mkdir(parents=True, exist_ok=False)

    contract = AcceptanceContract(
        goal=GOAL,
        goal_summary="实现、测试并提供独立最终证据的计算器",
        criteria=[
            GoalCriterion("source", "calculator.py exists", "file_exists", path="calculator.py"),
            GoalCriterion("tests", "calculator tests pass", "command", command="python -m unittest -v test_calculator.py"),
            GoalCriterion("final_evidence", "final verification report exists", "file_exists", path="FINAL_EVIDENCE.md"),
        ],
        constraints=["All acceptance claims require run-provenanced tool evidence"],
    )
    baseline = Plan(
        GOAL,
        [
            SubTask(
                "implement_and_test",
                "developer",
                "Create calculator.py and test_calculator.py, then run python -m unittest -v test_calculator.py until it passes. Do not create FINAL_EVIDENCE.md.",
                metadata={
                    "required_tools": ["file_editor", "shell_runner", "test_runner"],
                    "expected_outputs": ["calculator.py", "test_calculator.py"],
                    "checks": [{"id": "baseline_tests", "check_type": "command", "command": "python -m unittest -v test_calculator.py"}],
                },
            ),
            SubTask(
                "audit_final_evidence",
                "reviewer",
                "Audit whether FINAL_EVIDENCE.md exists. Report the omission without creating or repairing it.",
                depends_on=["implement_and_test"],
                metadata={"required_tools": [], "expected_outputs": [], "checks": [{"id": "audit", "check_type": "manual"}]},
            ),
        ],
    )
    initial_plan = ContractAwarePlanner().build(contract, baseline)
    evaluator = StructuredGlobalEvaluator(client, contract, workspace)
    controller = LongHorizonController(
        Orchestrator(build_registry(client, workspace), max_workers=3),
        lambda _state: initial_plan,
        LongHorizonStore(demo_root),
        evaluator=evaluator,
        replanner=StructuredReplanner(client),
        max_phases=3,
        max_total_tasks=12,
        acceptance_contract=contract.to_dict(),
    )
    report = controller.run(GOAL, run_id=run_id)
    state = report.state
    print(f"run_id={run_id} status={state.status} phases={state.phase}")
    print(f"state={controller.store.state_path(run_id)}")
    if not state.phases or "final_evidence" not in state.phases[0].evaluation.get("missing_criteria", []):
        raise RuntimeError("phase one did not record the intended missing final_evidence criterion")
    if state.status != "completed" or state.phase < 2:
        raise RuntimeError("real two-phase demonstration did not complete")
    print("verified: phase 1 omission triggered replanning and a later phase completed the contract")


if __name__ == "__main__":
    main()
