"""Run a reproducible real-model two-phase long-horizon demonstration.

Required environment variables: MODEL_BASE_URL, MODEL_API_KEY, MODEL_NAME.
The key is read only from process memory and is never persisted.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
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
    started = time.perf_counter()
    report = controller.run(GOAL, run_id=run_id)
    duration = time.perf_counter() - started
    state = report.state
    records = [record for record in state.evidence_records if record.get("call_type") == "model_call"]
    usage_rows = [record.get("usage") for record in records]
    usage_complete = bool(usage_rows) and all(isinstance(row, dict) and row for row in usage_rows)
    if usage_complete:
        prompt_tokens = sum(int(row.get("prompt_tokens", row.get("input_tokens", 0))) for row in usage_rows)
        completion_tokens = sum(int(row.get("completion_tokens", row.get("output_tokens", 0))) for row in usage_rows)
        total_tokens = sum(int(row.get("total_tokens", int(row.get("prompt_tokens", row.get("input_tokens", 0))) + int(row.get("completion_tokens", row.get("output_tokens", 0))))) for row in usage_rows)
    else:
        prompt_tokens = completion_tokens = total_tokens = None
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parent, check=True,
                                capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    parts = urlsplit(client.config.base_url)
    endpoint = f"{parts.scheme}://{parts.hostname}" if parts.hostname else "unknown"
    artifacts = []
    for relative in state.artifacts:
        candidate = (workspace / relative).resolve()
        if workspace.resolve() not in candidate.parents or not candidate.is_file():
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        artifacts.append({"path": relative, "sha256": digest, "size_bytes": candidate.stat().st_size})
    input_rate = os.getenv("MODEL_INPUT_USD_PER_MILLION")
    output_rate = os.getenv("MODEL_OUTPUT_USD_PER_MILLION")
    estimated_cost = None
    if prompt_tokens is not None and completion_tokens is not None and input_rate and output_rate:
        estimated_cost = round((prompt_tokens * float(input_rate) + completion_tokens * float(output_rate)) / 1_000_000, 8)
    evidence = {
        "schema_version": "1.0",
        "run_id": run_id,
        "evidence_kind": "live_real_run",
        "candidate_tag": os.getenv("CANDIDATE_TAG", "unreleased_worktree"),
        "candidate_commit": commit,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": client.config.model,
        "endpoint_redacted": endpoint,
        "status": state.status,
        "phase_count": state.phase,
        "duration_seconds": round(duration, 3),
        "model_call_count": len(records),
        "token_usage_status": "reported" if usage_complete else "unknown",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": estimated_cost,
        "cost_status": "estimated" if estimated_cost is not None else "unknown",
        "phases": [
            {"number": phase.number, "status": phase.status, "report_status": phase.report_status,
             "missing_criteria": phase.evaluation.get("missing_criteria", []),
             "local_recovery_cycles": phase.local_recovery_cycles,
             "executed_task_count": phase.executed_task_count}
            for phase in state.phases
        ],
        "artifact_hashes": artifacts,
    }
    (workspace.parent / "live_run_evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"run_id={run_id} status={state.status} phases={state.phase}")
    print(f"state={controller.store.state_path(run_id)}")
    print(f"live_evidence={workspace.parent / 'live_run_evidence.json'}")
    if not state.phases or "final_evidence" not in state.phases[0].evaluation.get("missing_criteria", []):
        raise RuntimeError("phase one did not record the intended missing final_evidence criterion")
    if state.status != "completed" or state.phase < 2:
        raise RuntimeError("real two-phase demonstration did not complete")
    print("verified: phase 1 omission triggered replanning and a later phase completed the contract")


if __name__ == "__main__":
    main()
