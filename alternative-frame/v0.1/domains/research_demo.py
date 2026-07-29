"""First-stage offline research domain adapter.

The adapter delegates all measurable work to workspace-scoped tools. It does
not implement a second orchestrator or long-horizon state machine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from core.agents import Agent
from core.domains import DomainAdapter
from core.long_horizon import AcceptanceContract, GoalCriterion
from core.models import AgentResult, Plan, SubTask, utc_now
from core.tools import ExperimentRunner, ShellRunner, ToolRegistry

from .research_tools import DatasetInspector


GENERATOR_COMMAND = "python generate_dataset.py --output data/dataset.json"
BASELINE_COMMAND = (
    "python run_baseline.py --dataset data/dataset.json "
    "--output artifacts/baseline_metrics.json"
)


class ResearchExecutionAgent(Agent):
    """Thin deterministic dispatcher; tools, not prose, produce all metrics."""

    def __init__(self, role: str, tools: ToolRegistry, workspace: Path):
        self.role = role
        self.tools = tools
        self.workspace = workspace

    def run(
        self,
        task: SubTask,
        context: Mapping[str, AgentResult],
    ) -> AgentResult:
        started = utc_now()
        tool_name = str(task.metadata["execution"]["tool"])
        arguments = dict(task.metadata["execution"]["arguments"])
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
            evidence=[f"tool={result.tool};success={result.success}"],
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
    )

    def register_tools(self, registry: ToolRegistry, workspace: Path) -> None:
        self.workspace = workspace
        shell = ShellRunner(workspace, timeout_seconds=120)
        registry.register(ExperimentRunner(shell))
        registry.register(DatasetInspector(workspace))

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
                        },
                    },
                },
            ),
            SubTask(
                id="run_baseline",
                role="research_experiment",
                description="Fit and evaluate the nearest-centroid baseline.",
                depends_on=["inspect_dataset"],
                max_retries=0,
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
        ]
        return Plan(
            goal=goal,
            subtasks=tasks,
            final_acceptance=[
                "dataset_generated",
                "dataset_summary",
                "baseline_metrics",
                "baseline_accuracy",
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
            ],
            constraints=[
                "Offline execution only",
                "Python 3.10+ standard library only",
                "Dataset seed and split are fixed",
                "Metrics must come from an experiment tool call",
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
                target.unlink()
        (workspace_path / "data").mkdir(exist_ok=True)
        (workspace_path / "artifacts").mkdir(exist_ok=True)
