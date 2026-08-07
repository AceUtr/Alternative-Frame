"""First-stage offline research domain adapter.

The adapter delegates all measurable work to workspace-scoped tools. It does
not implement a second orchestrator or long-horizon state machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from core.agents import Agent
from core.domains import DomainAdapter
from core.long_horizon import (
    AcceptanceContract,
    DeterministicGlobalEvaluator,
    GoalCriterion,
)
from core.models import AgentResult, Plan, SubTask, utc_now
from core.tools import ExperimentRunner, ShellRunner, ToolRegistry

from .research_tools import DatasetInspector, MetricComparator, ResearchReportBuilder


GENERATOR_COMMAND = "python generate_dataset.py --output data/dataset.json"
BASELINE_COMMAND = (
    "python run_baseline.py --dataset data/dataset.json "
    "--output artifacts/baseline_metrics.json"
)
IMPROVED_COMMAND = (
    "python run_improved.py --dataset data/dataset.json "
    "--output artifacts/improved_metrics.json"
)
VERIFICATION_COMMAND = (
    "python verify_best.py --dataset data/dataset.json "
    "--config artifacts/best_config.json "
    "--output artifacts/verification_metrics.json --tolerance 0.000000001"
)
REPORT_ARGUMENTS = {
    "baseline_metrics_path": "artifacts/baseline_metrics.json",
    "improved_metrics_path": "artifacts/improved_metrics.json",
    "best_config_path": "artifacts/best_config.json",
    "verification_metrics_path": "artifacts/verification_metrics.json",
    "chart_path": "artifacts/comparison.png",
    "report_path": "artifacts/research_report.md",
}


class ResearchExecutionAgent(Agent):
    """Thin deterministic dispatcher; tools, not prose, produce all metrics."""

    def __init__(self, role: str, tools: ToolRegistry, workspace: Path):
        self.role = role
        self.tools = tools
        self.workspace = workspace
        self._fault_counts: dict[str, int] = {}

    def run(
        self,
        task: SubTask,
        context: Mapping[str, AgentResult],
    ) -> AgentResult:
        started = utc_now()
        fault = task.metadata.get("fault_injection", {})
        fault_count = 0
        if isinstance(fault, dict) and fault.get("enabled") is True:
            fault_id = str(fault.get("id", task.id))
            fail_attempts = int(fault.get("fail_attempts", 1))
            self._fault_counts[fault_id] = self._fault_counts.get(fault_id, 0) + 1
            fault_count = self._fault_counts[fault_id]
            if (
                fault.get("mode", "transient_failure") == "transient_failure"
                and fault_count <= fail_attempts
            ):
                return AgentResult(
                    subtask_id=task.id,
                    status="failed",
                    summary="Deterministic research fault injected before tool execution.",
                    evidence=[
                        f"fault_injection={fault_id};"
                        f"attempt={fault_count}"
                    ],
                    failures=["injected transient research failure"],
                    started_at=started,
                    finished_at=utc_now(),
                )
        tool_name = str(task.metadata["execution"]["tool"])
        arguments = dict(task.metadata["execution"]["arguments"])
        evidence = []
        if (
            isinstance(fault, dict)
            and fault.get("enabled") is True
            and fault.get("mode") == "argument_override"
            and fault_count <= int(fault.get("fail_attempts", 1))
        ):
            arguments.update(dict(fault.get("argument_overrides", {})))
            evidence.append(f"fault_argument_override=attempt:{fault_count}")
        retry_feedback = task.metadata.get("retry_feedback")
        repair = task.metadata.get("retry_repair", {})
        if isinstance(retry_feedback, dict) and isinstance(repair, dict):
            expected_category = repair.get("feedback_category")
            if expected_category in (None, retry_feedback.get("category")):
                for value in repair.get("cleanup_paths", []):
                    relative = Path(str(value))
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError(f"retry cleanup path escapes workspace: {value}")
                    target = (self.workspace / relative).resolve()
                    if target != self.workspace and self.workspace not in target.parents:
                        raise ValueError(f"retry cleanup path escapes workspace: {value}")
                    if target.is_file():
                        target.unlink()
                        evidence.append(
                            f"retry_artifact_removed={relative.as_posix()}"
                        )
                arguments.update(dict(repair.get("arguments", {})))
                evidence.append(
                    "retry_feedback_applied="
                    f"{retry_feedback.get('category', 'unknown')}"
                )
        result = self.tools.execute(tool_name, arguments)
        expected_outputs = list(task.metadata.get("expected_outputs", []))
        missing_outputs = [
            path for path in expected_outputs if not (self.workspace / path).is_file()
        ]
        if result.success and missing_outputs:
            result.success = False
            result.error = f"missing expected outputs: {missing_outputs}"
        if result.success and expected_outputs:
            result.metadata["artifacts"] = expected_outputs
        artifacts = list(result.metadata.get("artifacts", []))
        record = {
            "tool": result.tool,
            "arguments": arguments,
            "success": result.success,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
            "metadata": dict(result.metadata),
            "output_excerpt": (result.output or result.error)[:1000],
        }
        return AgentResult(
            subtask_id=task.id,
            status="success" if result.success else "failed",
            summary=f"{task.description} {result.output or result.error}".strip(),
            artifacts=artifacts,
            evidence=evidence + [f"tool={result.tool};success={result.success}"],
            tool_records=[record],
            failures=[] if result.success else [result.error],
            started_at=started,
            finished_at=utc_now(),
        )


class ResearchDomainAdapter(DomainAdapter):
    name = "research"
    _GENERATED_FILES = (
        "data/dataset.json",
        "artifacts/dataset_summary.json",
        "artifacts/baseline_metrics.json",
        "artifacts/improved_metrics.json",
        "artifacts/best_config.json",
        "artifacts/verification_metrics.json",
        "artifacts/comparison.png",
        "artifacts/research_report.md",
        "artifacts/fault_baseline_metrics.json",
    )

    def register_tools(self, registry: ToolRegistry, workspace: Path) -> None:
        self.workspace = workspace
        shell = ShellRunner(workspace, timeout_seconds=120)
        registry.register(ExperimentRunner(shell))
        registry.register(DatasetInspector(workspace))
        registry.register(MetricComparator(workspace))
        registry.register(ResearchReportBuilder(workspace))

    def build_agents(self, model_client, tools: ToolRegistry):
        return [
            ResearchExecutionAgent("research_data", tools, self.workspace),
            ResearchExecutionAgent("research_experiment", tools, self.workspace),
        ]

    def build_plan(self, goal: str) -> Plan:
        tasks = [
            SubTask(
                id="generate_dataset",
                role="research_data",
                description="Generate the fixed offline train/test dataset.",
                max_retries=0,
                metadata={
                    "required_tools": ["experiment_runner"],
                    "expected_outputs": ["data/dataset.json"],
                    "checks": [
                        {
                            "id": "dataset_generated",
                            "check_type": "file_exists",
                            "path": "data/dataset.json",
                        }
                    ],
                    "contract_criteria": ["dataset_generated"],
                    "execution": {
                        "tool": "experiment_runner",
                        "arguments": {"command": GENERATOR_COMMAND},
                    },
                },
            ),
            SubTask(
                id="inspect_dataset",
                role="research_data",
                description="Validate dataset schema, split and label distribution.",
                depends_on=["generate_dataset"],
                max_retries=0,
                metadata={
                    "required_tools": ["dataset_inspector"],
                    "expected_outputs": ["artifacts/dataset_summary.json"],
                    "checks": [
                        {
                            "id": "dataset_summary",
                            "check_type": "file_exists",
                            "path": "artifacts/dataset_summary.json",
                        }
                    ],
                    "contract_criteria": ["dataset_summary"],
                    "execution": {
                        "tool": "dataset_inspector",
                        "arguments": {
                            "dataset_path": "data/dataset.json",
                            "output_path": "artifacts/dataset_summary.json",
                            "required_fields": ["x1", "x2", "label"],
                            "field_types": {
                                "id": "integer",
                                "x1": "number",
                                "x2": "number",
                                "label": "integer",
                            },
                            "allowed_labels": [0, 1],
                            "required_provenance": ["source", "generator", "license"],
                        },
                    },
                },
            ),
            SubTask(
                id="run_baseline",
                role="research_experiment",
                description="Fit and evaluate the nearest-centroid baseline.",
                depends_on=["inspect_dataset"],
                max_retries=1,
                metadata={
                    "required_tools": ["experiment_runner"],
                    "expected_outputs": ["artifacts/baseline_metrics.json"],
                    "checks": [
                        {
                            "id": "baseline_metrics",
                            "check_type": "file_exists",
                            "path": "artifacts/baseline_metrics.json",
                        },
                        {
                            "id": "baseline_accuracy",
                            "check_type": "metric",
                            "metric_name": "accuracy",
                            "threshold": 0.8,
                            "mode": "max",
                        },
                    ],
                    "contract_criteria": [
                        "baseline_metrics",
                        "baseline_accuracy",
                    ],
                    "execution": {
                        "tool": "experiment_runner",
                        "arguments": {"command": BASELINE_COMMAND},
                    },
                },
            ),
            SubTask(
                id="run_improved",
                role="research_experiment",
                description="Fit and evaluate the two-feature improved configuration.",
                depends_on=["inspect_dataset"],
                max_retries=1,
                metadata={
                    "required_tools": ["experiment_runner"],
                    "expected_outputs": ["artifacts/improved_metrics.json"],
                    "checks": [
                        {
                            "id": "improved_metrics",
                            "check_type": "file_exists",
                            "path": "artifacts/improved_metrics.json",
                        },
                        {
                            "id": "improved_accuracy",
                            "check_type": "metric",
                            "metric_name": "accuracy",
                            "threshold": 0.9,
                            "mode": "max",
                        },
                    ],
                    "contract_criteria": ["improved_metrics", "improved_accuracy"],
                    "execution": {
                        "tool": "experiment_runner",
                        "arguments": {"command": IMPROVED_COMMAND},
                    },
                },
            ),
            SubTask(
                id="compare_experiments",
                role="research_experiment",
                description="Compare compatible baseline and improved metric files.",
                depends_on=["run_baseline", "run_improved"],
                max_retries=0,
                metadata={
                    "required_tools": ["metric_comparator"],
                    "expected_outputs": ["artifacts/best_config.json"],
                    "checks": [
                        {
                            "id": "best_config",
                            "check_type": "file_exists",
                            "path": "artifacts/best_config.json",
                        }
                    ],
                    "contract_criteria": ["best_config"],
                    "execution": {
                        "tool": "metric_comparator",
                        "arguments": {
                            "metric_files": [
                                "artifacts/baseline_metrics.json",
                                "artifacts/improved_metrics.json",
                            ],
                            "primary_metric": "accuracy",
                            "mode": "max",
                            "output_path": "artifacts/best_config.json",
                        },
                    },
                },
            ),
            SubTask(
                id="build_initial_report",
                role="research_experiment",
                description="Build the initial chart and report with verification pending.",
                depends_on=["compare_experiments"],
                max_retries=0,
                metadata={
                    "required_tools": ["research_report_builder"],
                    "expected_outputs": [
                        "artifacts/comparison.png",
                        "artifacts/research_report.md",
                    ],
                    "checks": [
                        {
                            "id": "comparison_chart",
                            "check_type": "file_exists",
                            "path": "artifacts/comparison.png",
                        },
                        {
                            "id": "research_report",
                            "check_type": "file_exists",
                            "path": "artifacts/research_report.md",
                        },
                        {
                            "id": "improvement_delta",
                            "check_type": "metric",
                            "metric_name": "improvement_delta",
                            "threshold": 0.000001,
                            "mode": "max",
                        },
                    ],
                    "contract_criteria": [
                        "comparison_chart",
                        "research_report",
                        "improvement_delta",
                    ],
                    "execution": {
                        "tool": "research_report_builder",
                        "arguments": dict(REPORT_ARGUMENTS),
                    },
                },
            ),
        ]
        return Plan(
            goal=goal,
            subtasks=tasks,
            final_acceptance=[
                "dataset_generated",
                "dataset_summary",
                "baseline_metrics",
                "baseline_accuracy",
                "improved_metrics",
                "improved_accuracy",
                "best_config",
                "improvement_delta",
                "comparison_chart",
                "research_report",
            ],
        )

    def build_contract(self, goal: str) -> AcceptanceContract:
        return AcceptanceContract(
            goal=goal,
            goal_summary="Generate, inspect and execute a reproducible offline baseline",
            criteria=[
                GoalCriterion(
                    "dataset_generated",
                    "Fixed dataset exists with run provenance",
                    "file_exists",
                    path="data/dataset.json",
                ),
                GoalCriterion(
                    "dataset_summary",
                    "Dataset inspection summary exists",
                    "file_exists",
                    path="artifacts/dataset_summary.json",
                ),
                GoalCriterion(
                    "baseline_metrics",
                    "Baseline metrics JSON exists",
                    "file_exists",
                    path="artifacts/baseline_metrics.json",
                ),
                GoalCriterion(
                    "baseline_accuracy",
                    "Baseline reaches the declared minimum accuracy",
                    "metric",
                    metric_name="accuracy",
                    threshold=0.8,
                ),
                GoalCriterion(
                    "improved_metrics",
                    "Improved metrics JSON exists",
                    "file_exists",
                    path="artifacts/improved_metrics.json",
                ),
                GoalCriterion(
                    "improved_accuracy",
                    "Improved experiment reaches the declared accuracy",
                    "metric",
                    metric_name="accuracy",
                    threshold=0.9,
                ),
                GoalCriterion(
                    "best_config",
                    "Best configuration is selected from compatible metrics",
                    "file_exists",
                    path="artifacts/best_config.json",
                ),
                GoalCriterion(
                    "improvement_delta",
                    "Improved accuracy is strictly better than baseline accuracy",
                    "metric",
                    metric_name="improvement_delta",
                    threshold=0.000001,
                ),
                GoalCriterion(
                    "verification_metrics",
                    "Best configuration is independently rerun",
                    "file_exists",
                    path="artifacts/verification_metrics.json",
                ),
                GoalCriterion(
                    "verification_command",
                    "Independent verification command exits successfully",
                    "command",
                    command=VERIFICATION_COMMAND,
                ),
                GoalCriterion(
                    "comparison_chart",
                    "Metric comparison chart exists",
                    "file_exists",
                    path="artifacts/comparison.png",
                ),
                GoalCriterion(
                    "research_report",
                    "Research report exists",
                    "file_exists",
                    path="artifacts/research_report.md",
                ),
            ],
            constraints=[
                "Offline execution only",
                "Python 3.10+ standard library only",
                "Dataset seed and split are fixed",
                "Metrics must come from an experiment tool call",
            ],
        )

    def build_recovery_plan(self, goal: str) -> Plan:
        """Build phase two that fills the real independent-verification gap."""
        return Plan(
            goal=goal,
            subtasks=[
                SubTask(
                    id="verify_best",
                    role="research_experiment",
                    description="Independently rerun the selected best configuration.",
                    max_retries=1,
                    metadata={
                        "required_tools": ["experiment_runner"],
                        "expected_outputs": ["artifacts/verification_metrics.json"],
                        "checks": [
                            {
                                "id": "verification_metrics",
                                "check_type": "file_exists",
                                "path": "artifacts/verification_metrics.json",
                            },
                            {
                                "id": "verification_accuracy",
                                "check_type": "metric",
                                "metric_name": "accuracy",
                                "threshold": 0.9,
                                "mode": "max",
                            },
                            {
                                "id": "verification_command",
                                "check_type": "command",
                                "command": VERIFICATION_COMMAND,
                            },
                        ],
                        "contract_criteria": [
                            "verification_metrics",
                            "verification_accuracy",
                            "verification_command",
                        ],
                        "execution": {
                            "tool": "experiment_runner",
                            "arguments": {"command": VERIFICATION_COMMAND},
                        },
                    },
                ),
                SubTask(
                    id="update_research_report",
                    role="research_experiment",
                    description="Update chart and report with independent verification evidence.",
                    depends_on=["verify_best"],
                    max_retries=0,
                    metadata={
                        "required_tools": ["research_report_builder"],
                        "expected_outputs": [
                            "artifacts/comparison.png",
                            "artifacts/research_report.md",
                        ],
                        "checks": [
                            {
                                "id": "comparison_chart",
                                "check_type": "file_exists",
                                "path": "artifacts/comparison.png",
                            },
                            {
                                "id": "research_report",
                                "check_type": "file_exists",
                                "path": "artifacts/research_report.md",
                            },
                        ],
                        "contract_criteria": ["comparison_chart", "research_report"],
                        "execution": {
                            "tool": "research_report_builder",
                            "arguments": dict(REPORT_ARGUMENTS),
                        },
                    },
                ),
            ],
            final_acceptance=[
                "verification_metrics",
                "verification_command",
                "comparison_chart",
                "research_report",
            ],
        )

    def reset_workspace(self, workspace: Path) -> None:
        """Remove only known generated outputs and preserve fixture source files."""
        workspace_path = Path(workspace).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)
        for relative in self._GENERATED_FILES:
            target = (workspace_path / relative).resolve()
            if target != workspace_path and workspace_path not in target.parents:
                raise ValueError(f"generated path escapes workspace: {relative}")
            if target.is_file():
                try:
                    target.unlink()
                except PermissionError as exc:
                    raise RuntimeError(
                        f"cannot reset locked research output: {target}"
                    ) from exc
        (workspace_path / "data").mkdir(exist_ok=True)
        (workspace_path / "artifacts").mkdir(exist_ok=True)


class ResearchGlobalEvaluator(DeterministicGlobalEvaluator):
    """Fail-closed content audit layered over the shared hard-evidence gate."""

    def evaluate(self, state, plan, report):
        evaluation = super().evaluate(state, plan, report)
        if not evaluation.completed:
            return evaluation
        failures = self._audit_outputs()
        if not failures:
            return evaluation
        evaluation.completed = False
        evaluation.reason = "research artifact content audit did not pass"
        evaluation.missing_criteria = list(failures)
        evaluation.failures.extend(
            f"{criterion}: research artifact content invalid"
            for criterion in failures
        )
        evaluation.next_focus = [
            f"repair research artifact criterion: {criterion}"
            for criterion in failures
        ]
        return evaluation

    def _audit_outputs(self):
        import json
        import math

        workspace = self.hard_gate.workspace
        failures = []
        try:
            baseline = json.loads(
                (workspace / "artifacts/baseline_metrics.json").read_text(
                    encoding="utf-8"
                )
            )
            improved = json.loads(
                (workspace / "artifacts/improved_metrics.json").read_text(
                    encoding="utf-8"
                )
            )
            verification = json.loads(
                (workspace / "artifacts/verification_metrics.json").read_text(
                    encoding="utf-8"
                )
            )
            best = json.loads(
                (workspace / "artifacts/best_config.json").read_text(
                    encoding="utf-8"
                )
            )
            baseline_score = float(baseline["accuracy"])
            improved_score = float(improved["accuracy"])
            verified_score = float(verification["accuracy"])
            best_score = float(best["best_score"])
            tolerance = float(verification["verification_tolerance"])
            if not all(
                math.isfinite(value)
                for value in (
                    baseline_score,
                    improved_score,
                    verified_score,
                    best_score,
                    tolerance,
                )
            ):
                raise ValueError("research metrics must be finite")
            if improved_score - baseline_score < 0.000001:
                failures.append("improvement_delta")
            if (
                verification.get("verification_passed") is not True
                or abs(verified_score - best_score) > tolerance
            ):
                failures.append("verification_metrics")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            failures.extend(["baseline_metrics", "improved_metrics", "verification_metrics"])

        chart = workspace / "artifacts/comparison.png"
        try:
            if chart.stat().st_size <= 8 or not chart.read_bytes().startswith(
                b"\x89PNG\r\n\x1a\n"
            ):
                failures.append("comparison_chart")
        except OSError:
            failures.append("comparison_chart")

        try:
            report_text = (workspace / "artifacts/research_report.md").read_text(
                encoding="utf-8"
            )
            required_text = (
                f"{baseline_score:.6f}",
                f"{improved_score:.6f}",
                f"{verified_score:.6f}",
                "Independent verification: **passed**",
            )
            if any(item not in report_text for item in required_text):
                failures.append("research_report")
        except (OSError, UnboundLocalError):
            failures.append("research_report")
        return list(dict.fromkeys(failures))
