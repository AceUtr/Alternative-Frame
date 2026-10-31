"""Controlled recovery ablation using the real two-phase demo.

Modes:
    none  - no local recovery, no phase replanning
    phase - phase replanning only
    full  - phase replanning plus local DAG recovery

This experiment uses a deterministic phase-one contract omission.
It directly tests phase-level recovery. A separate local-failure
experiment is required to measure the incremental benefit of local DAG
recovery.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from core.agents import Agent, AgentRegistry
from core.evaluation.recovery_modes import (
    build_local_recovery,
    build_replanner,
    get_recovery_settings,
)
from core.long_horizon import (
    AcceptanceContract,
    ContractAwarePlanner,
    GoalCriterion,
    LongHorizonController,
    LongHorizonStore,
    StructuredGlobalEvaluator,
    StructuredReplanner,
)
from core.metrics import metrics_from_long_horizon
from core.model_client import ModelConfig, OpenAICompatibleClient
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator
from core.tool_calling_agent import ToolCallingAgent
from core.tools import (
    FileEditor,
    GitClient,
    ShellRunner,
    TestRunner,
    ToolRegistry,
)


GOAL = (
    "Implement a testable addition calculator, verify it with automated "
    "tests, and provide FINAL_EVIDENCE.md as the final verification report."
)


class AuditThenDelegate(Agent):
    """Make the phase-one contract omission deterministic."""

    role = "reviewer"

    def __init__(self, delegate):
        self.delegate = delegate

    def run(self, task, context):
        if task.id == "audit_final_evidence":
            return AgentResult(
                task.id,
                "success",
                summary=(
                    "Independent audit: FINAL_EVIDENCE.md is missing; "
                    "intentionally did not repair it."
                ),
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
            (
                "Complete the assigned task with real workspace tools "
                "and preserve concise verification evidence."
            ),
            max_steps=16,
        )

        registry.register(
            AuditThenDelegate(agent)
            if role == "reviewer"
            else agent
        )

    return registry


def build_contract():
    return AcceptanceContract(
        goal=GOAL,
        goal_summary=(
            "Implement, test, and independently verify the calculator."
        ),
        criteria=[
            GoalCriterion(
                "source",
                "calculator.py exists",
                "file_exists",
                path="calculator.py",
            ),
            GoalCriterion(
                "tests",
                "calculator tests pass",
                "command",
                command="python -m unittest -v test_calculator.py",
            ),
            GoalCriterion(
                "final_evidence",
                "final verification report exists",
                "file_exists",
                path="FINAL_EVIDENCE.md",
            ),
        ],
        constraints=[
            "All acceptance claims require run-provenanced tool evidence"
        ],
    )


def build_initial_plan(contract):
    baseline = Plan(
        GOAL,
        [
            SubTask(
                "implement_and_test",
                "developer",
                (
                    "Create calculator.py and test_calculator.py, then run "
                    "python -m unittest -v test_calculator.py until it "
                    "passes. Do not create FINAL_EVIDENCE.md."
                ),
                metadata={
                    "required_tools": [
                        "file_editor",
                        "shell_runner",
                        "test_runner",
                    ],
                    "expected_outputs": [
                        "calculator.py",
                        "test_calculator.py",
                    ],
                    "checks": [
                        {
                            "id": "baseline_tests",
                            "check_type": "command",
                            "command": (
                                "python -m unittest -v "
                                "test_calculator.py"
                            ),
                        }
                    ],
                },
            ),
            SubTask(
                "audit_final_evidence",
                "reviewer",
                (
                    "Audit whether FINAL_EVIDENCE.md exists. "
                    "Report the omission without creating or repairing it."
                ),
                depends_on=["implement_and_test"],
                metadata={
                    "required_tools": [],
                    "expected_outputs": [],
                    "checks": [
                        {
                            "id": "audit",
                            "check_type": "manual",
                        }
                    ],
                },
            ),
        ],
    )

    return ContractAwarePlanner().build(contract, baseline)


def run_one(mode: str, output_root: Path):
    settings = get_recovery_settings(mode)

    client = OpenAICompatibleClient(
        ModelConfig.from_env()
    )

    run_id = (
        f"ablation_{mode}_"
        + uuid4().hex[:8]
    )

    run_root = output_root / mode
    run_root.mkdir(parents=True, exist_ok=True)

    workspace = run_root / run_id / "workspace"
    workspace.mkdir(parents=True, exist_ok=False)

    contract = build_contract()
    initial_plan = build_initial_plan(contract)

    registry = build_registry(
        client,
        workspace,
    )

    orchestrator = Orchestrator(
        registry,
        max_workers=3,
    )

    real_replanner = StructuredReplanner(client)

    replanner = build_replanner(
        mode,
        real_replanner,
    )

    local_recovery = build_local_recovery(
        mode,
        orchestrator,
    )

    store = LongHorizonStore(run_root)

    evaluator = StructuredGlobalEvaluator(
        client,
        contract,
        workspace,
    )

    controller = LongHorizonController(
        orchestrator,
        lambda _state: initial_plan,
        store,
        evaluator=evaluator,
        replanner=replanner,
        max_phases=settings.max_phases,
        max_total_tasks=12,
        acceptance_contract=contract.to_dict(),
        local_recovery=local_recovery,
    )

    report = controller.run(
        GOAL,
        run_id=run_id,
    )

    events = []

    events_path = store.events_path(run_id)

    if events_path.exists():
        for line in events_path.read_text(
            encoding="utf-8"
        ).splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))

    metrics = metrics_from_long_horizon(
        report.state,
        report.phase_reports,
        domain="calculator_ablation",
        mode=mode,
        model=os.getenv("MODEL_NAME", "unknown"),
        events=events,
    )

    return {
        "mode": mode,
        "run_id": run_id,
        "status": report.state.status,
        "goal_completed": metrics.final_goal_completed,
        "phase_count": metrics.phase_count,
        "task_count": metrics.task_count,
        "success_count": metrics.success_count,
        "failed_count": metrics.failed_count,
        "first_pass_count": metrics.first_pass_count,
        "local_recovery_count": metrics.local_recovery_count,
        "duration_seconds": metrics.duration_seconds,
        "total_tokens": metrics.total_tokens,
        "estimated_cost": metrics.estimated_cost,
        "state_path": str(
            store.state_path(run_id).resolve()
        ),
        "events_path": str(
            events_path.resolve()
        ),
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--modes",
        nargs="+",
        choices=["none", "phase", "full"],
        default=["none", "phase", "full"],
    )

    parser.add_argument(
        "--output-root",
        default="runs/recovery_ablation",
    )

    args = parser.parse_args()

    output_root = Path(args.output_root)
    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    results = []

    for mode in args.modes:
        print()
        print(
            f"=== recovery ablation: {mode} ===",
            flush=True,
        )

        result = run_one(
            mode,
            output_root,
        )

        results.append(result)

        print(
            f"mode={mode} "
            f"status={result['status']} "
            f"completed={result['goal_completed']} "
            f"phases={result['phase_count']} "
            f"local_recovery="
            f"{result['local_recovery_count']}",
            flush=True,
        )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    result_path = (
        output_root
        / f"ablation-{timestamp}.json"
    )

    result_path.write_text(
        json.dumps(
            {
                "experiment": "recovery_ablation",
                "evidence_kind": "live_real_run",
                "modes": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"results={result_path.resolve()}"
    )

    print()
    print(
        "NOTE: this phase-omission experiment directly "
        "measures phase-level recovery. Do not interpret "
        "a zero local-recovery count as evidence that "
        "local DAG recovery is ineffective."
    )


if __name__ == "__main__":
    main()
