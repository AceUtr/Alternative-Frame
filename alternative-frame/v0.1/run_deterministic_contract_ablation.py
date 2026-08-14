"""Deterministic contract-validation ablation.

This experiment requires no model API.

Both modes receive the same successful phase report.
The workspace intentionally omits FINAL_EVIDENCE.md.

contract_off:
    ReportStatusEvaluator only checks phase execution status.
    It therefore accepts the run as completed.

contract_on:
    DeterministicGlobalEvaluator checks the AcceptanceContract.
    Missing FINAL_EVIDENCE.md causes the run to remain incomplete.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from core.long_horizon import (
    AcceptanceContract,
    GoalCriterion,
)
from core.long_horizon.evaluator import ReportStatusEvaluator
from core.long_horizon.global_evaluator import DeterministicGlobalEvaluator
from core.long_horizon.state import LongHorizonState
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import RunReport


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_contract() -> AcceptanceContract:
    return AcceptanceContract(
        goal="Produce verified calculator delivery.",
        goal_summary="Calculator implementation, tests, and final evidence.",
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
                "FINAL_EVIDENCE.md exists",
                "file_exists",
                path="FINAL_EVIDENCE.md",
            ),
        ],
        constraints=[
            "Completion requires evidence for all required criteria."
        ],
    )


def build_plan() -> Plan:
    return Plan(
        "Implement and test calculator.",
        [
            SubTask(
                "implement",
                "developer",
                "Create calculator.py.",
            ),
            SubTask(
                "test",
                "tester",
                "Run calculator tests.",
                depends_on=["implement"],
            ),
        ],
    )


def build_success_report(plan: Plan) -> RunReport:
    """Build a green phase report with real-format provenance.

    calculator.py and the exact test command are deliberately proven.
    FINAL_EVIDENCE.md is deliberately absent.
    """
    started = utc_now()

    results = {
        "implement": AgentResult(
            "implement",
            "success",
            summary="calculator.py created",
            artifacts=["calculator.py"],
        ),
        "test": AgentResult(
            "test",
            "success",
            summary="calculator tests passed",
            tool_records=[
                {
                    "tool": "test_runner",
                    "arguments": {
                        "command": (
                            "python -m unittest -v "
                            "test_calculator.py"
                        )
                    },
                    "success": True,
                    "exit_code": 0,
                }
            ],
        ),
    }

    finished = utc_now()

    return RunReport(
        goal=plan.goal,
        status="success",
        results=results,
        rounds=1,
        started_at=started,
        finished_at=finished,
        failures=[],
        executed_task_count=2,
        local_recovery_cycles=0,
    )

def build_state(run_id: str) -> LongHorizonState:
    now = utc_now()

    return LongHorizonState(
        run_id=run_id,
        goal="Produce verified calculator delivery.",
        status="running",
        phase=0,
        max_phases=1,
        max_total_tasks=10,
        total_tasks=2,
        completed_tasks=[],
        failed_tasks=[],
        created_at=now,
        updated_at=now,
    )


def prepare_workspace(workspace: Path) -> None:
    workspace.mkdir(
        parents=True,
        exist_ok=True,
    )

    (workspace / "calculator.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    (workspace / "test_calculator.py").write_text(
        "import unittest\n"
        "from calculator import add\n\n"
        "class CalculatorTests(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8",
    )

    # Deliberately DO NOT create FINAL_EVIDENCE.md


@dataclass
class ContractAblationResult:
    mode: str
    completed: bool
    reason: str
    satisfied_criteria: List[str]
    missing_criteria: List[str]
    failures: List[str]
    phase_report_status: str
    evidence_kind: str = "deterministic_controlled_run"


def run_mode(mode: str) -> ContractAblationResult:
    if mode not in {"contract_off", "contract_on"}:
        raise ValueError(
            "mode must be contract_off or contract_on"
        )

    with tempfile.TemporaryDirectory(
        prefix="contract_ablation_"
    ) as temp:
        workspace = Path(temp)

        prepare_workspace(workspace)

        plan = build_plan()
        report = build_success_report(plan)
        state = build_state(
            f"deterministic_{mode}"
        )

        if mode == "contract_off":
            evaluator = ReportStatusEvaluator()
        else:
            evaluator = DeterministicGlobalEvaluator(
                build_contract(),
                workspace,
            )

        evaluation = evaluator.evaluate(
            state,
            plan,
            report,
        )

        return ContractAblationResult(
            mode=mode,
            completed=evaluation.completed,
            reason=evaluation.reason,
            satisfied_criteria=list(
                getattr(
                    evaluation,
                    "satisfied_criteria",
                    [],
                )
                or []
            ),
            missing_criteria=list(
                getattr(
                    evaluation,
                    "missing_criteria",
                    [],
                )
                or []
            ),
            failures=list(
                getattr(
                    evaluation,
                    "failures",
                    [],
                )
                or []
            ),
            phase_report_status=report.status,
        )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        default=(
            "benchmarks/configs/"
            "deterministic_contract.json"
        ),
    )

    args = parser.parse_args()

    config = json.loads(
        Path(args.config).read_text(
            encoding="utf-8-sig"
        )
    )

    results = []

    for mode in config.get(
        "modes",
        ["contract_off", "contract_on"],
    ):
        result = run_mode(mode)

        results.append(
            asdict(result)
        )

        print(
            f"{mode}: "
            f"phase_status={result.phase_report_status} "
            f"completed={result.completed} "
            f"missing={result.missing_criteria}"
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
            "deterministic_contract-"
            f"{timestamp}.json"
        )
    )

    output_path.write_text(
        json.dumps(
            {
                "experiment": config.get(
                    "name",
                    "deterministic_contract_ablation",
                ),
                "evidence_kind": (
                    "deterministic_controlled_run"
                ),
                "generated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "results": results,
            },
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

