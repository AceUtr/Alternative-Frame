"""Deterministic local-recovery ablation.

This experiment requires no model API.

DAG:
    prepare -> compute -> verify

The first execution of `compute` fails deterministically.

recovery_off:
    execute original DAG once; final result remains failed.

recovery_on:
    LocalDAGRecoveryController identifies compute + verify as impacted,
    freezes prepare, reruns only the impacted subgraph, and succeeds.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from core.local_recovery import LocalDAGRecoveryController
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import RunReport


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeRegistry:
    def roles(self):
        return ["worker"]


class DeterministicFailureOrchestrator:
    """Fail compute exactly once across the lifetime of this orchestrator."""

    def __init__(self):
        self.registry = FakeRegistry()
        self.task_attempts: Dict[str, int] = {}
        self.execution_log: List[str] = []

    def run(self, plan: Plan) -> RunReport:
        started = utc_now()
        results: Dict[str, AgentResult] = {}
        failures: List[str] = []

        for task in plan.subtasks:
            # Mimic dependency blocking.
            blocked = any(
                dep not in results
                or results[dep].status != "success"
                for dep in task.depends_on
            )

            if blocked:
                continue

            self.execution_log.append(task.id)

            attempt = self.task_attempts.get(task.id, 0) + 1
            self.task_attempts[task.id] = attempt

            if task.id == "compute" and attempt == 1:
                result = AgentResult(
                    task.id,
                    "failed",
                    summary="Deterministic injected failure on first compute attempt.",
                    failures=["injected_compute_failure"],
                    attempts=attempt,
                )
            else:
                result = AgentResult(
                    task.id,
                    "success",
                    summary=f"{task.id} completed successfully.",
                    evidence=["deterministic_test_evidence"],
                    attempts=attempt,
                )

            results[task.id] = result

            if result.status != "success":
                failures.append(
                    f"{task.id}: {', '.join(result.failures) or result.status}"
                )

        # Mark downstream tasks blocked by a failed dependency.
        missing = [
            task.id
            for task in plan.subtasks
            if task.id not in results
        ]

        failures.extend(
            f"{task_id}: blocked by failed dependency"
            for task_id in missing
        )

        finished = utc_now()

        return RunReport(
            goal=plan.goal,
            status=(
                "success"
                if not failures and len(results) == len(plan.subtasks)
                else "failed"
            ),
            results=results,
            rounds=1,
            started_at=started,
            finished_at=finished,
            failures=failures,
            executed_task_count=len(results),
            local_recovery_cycles=0,
        )


def build_plan() -> Plan:
    return Plan(
        "Complete deterministic three-node DAG.",
        [
            SubTask(
                "prepare",
                "worker",
                "Prepare deterministic input.",
            ),
            SubTask(
                "compute",
                "worker",
                "Perform deterministic computation.",
                depends_on=["prepare"],
            ),
            SubTask(
                "verify",
                "worker",
                "Verify deterministic computation.",
                depends_on=["compute"],
            ),
        ],
    )


@dataclass
class ExperimentResult:
    mode: str
    status: str
    goal_completed: bool

    original_task_count: int
    final_success_count: int
    final_failed_count: int

    local_recovery_count: int
    executed_task_count: int
    extra_executions: int

    prepare_attempts: int
    compute_attempts: int
    verify_attempts: int

    execution_log: List[str]
    frozen_prepare: bool

    evidence_kind: str = "deterministic_controlled_run"


def run_mode(mode: str, task_budget: int = 10) -> ExperimentResult:
    if mode not in {"recovery_off", "recovery_on"}:
        raise ValueError(
            "mode must be recovery_off or recovery_on"
        )

    plan = build_plan()
    orchestrator = DeterministicFailureOrchestrator()

    if mode == "recovery_off":
        report = orchestrator.run(plan)
        local_recovery_count = 0

    else:
        events = []

        controller = LocalDAGRecoveryController(
            orchestrator,
            max_cycles=1,
            on_event=lambda event, payload: events.append(
                {
                    "event": event,
                    "payload": payload,
                }
            ),
        )

        outcome = controller.run(
            plan,
            task_budget=task_budget,
        )

        report = outcome.report
        local_recovery_count = outcome.cycles

    final_success_count = sum(
        result.status == "success"
        for result in report.results.values()
    )

    final_failed_count = (
        len(plan.subtasks) - final_success_count
    )

    executed_task_count = int(
        getattr(
            report,
            "executed_task_count",
            len(orchestrator.execution_log),
        )
        or len(orchestrator.execution_log)
    )

    prepare_attempts = orchestrator.task_attempts.get(
        "prepare", 0
    )
    compute_attempts = orchestrator.task_attempts.get(
        "compute", 0
    )
    verify_attempts = orchestrator.task_attempts.get(
        "verify", 0
    )

    return ExperimentResult(
        mode=mode,
        status=report.status,
        goal_completed=report.status == "success",

        original_task_count=len(plan.subtasks),
        final_success_count=final_success_count,
        final_failed_count=final_failed_count,

        local_recovery_count=local_recovery_count,
        executed_task_count=executed_task_count,
        extra_executions=max(
            len(orchestrator.execution_log)
            - len(plan.subtasks),
            0,
        ),

        prepare_attempts=prepare_attempts,
        compute_attempts=compute_attempts,
        verify_attempts=verify_attempts,

        execution_log=list(
            orchestrator.execution_log
        ),

        # Strong local-recovery invariant:
        # successful prepare must not be rerun.
        frozen_prepare=prepare_attempts == 1,
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        default=(
            "benchmarks/configs/"
            "deterministic_recovery.json"
        ),
    )

    args = parser.parse_args()

    config = json.loads(
        Path(args.config).read_text(
            encoding="utf-8-sig"
        )
    )

    task_budget = int(
        config.get("task_budget", 10)
    )

    results = []

    for mode in config.get(
        "modes",
        ["recovery_off", "recovery_on"],
    ):
        result = run_mode(
            mode,
            task_budget=task_budget,
        )

        results.append(
            asdict(result)
        )

        print(
            f"{mode}: "
            f"status={result.status} "
            f"completed={result.goal_completed} "
            f"recovery={result.local_recovery_count} "
            f"executions={result.execution_log}"
        )

    output_dir = Path(
        "benchmarks/results/summary"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    output_path = (
        output_dir
        / (
            "deterministic_recovery-"
            f"{timestamp}.json"
        )
    )

    payload = {
        "experiment": config.get(
            "name",
            "deterministic_local_recovery",
        ),
        "evidence_kind": (
            "deterministic_controlled_run"
        ),
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "results": results,
    }

    output_path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"results={output_path.resolve()}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
