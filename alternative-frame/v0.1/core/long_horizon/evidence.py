from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from ..orchestrator import RunReport
from .acceptance_contract import AcceptanceContract, GoalCriterion
from .state import LongHorizonState


@dataclass
class EvidenceBundle:
    report_status: str
    task_results: Dict[str, Dict[str, Any]]
    artifacts: List[str]
    tool_records: List[Dict[str, Any]]
    failures: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def collect(cls, state: LongHorizonState, report: RunReport) -> "EvidenceBundle":
        current_artifacts = [artifact for result in report.results.values() for artifact in result.artifacts]
        current_records = [record for result in report.results.values() for record in result.tool_records]
        artifacts = list(dict.fromkeys(list(state.artifacts) + current_artifacts))
        return cls(
            report_status=report.status,
            task_results={
                task_id: {
                    "status": result.status,
                    "summary": result.summary[:1000],
                    "artifacts": list(result.artifacts),
                    "failures": list(result.failures),
                }
                for task_id, result in report.results.items()
            },
            artifacts=artifacts,
            tool_records=list(state.evidence_records) + current_records,
            failures=list(report.failures),
        )


@dataclass
class CriterionResult:
    criterion_id: str
    status: str  # passed / failed / deferred
    reason: str
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HardGateReport:
    passed: bool
    results: List[CriterionResult]
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "results": [result.to_dict() for result in self.results],
            "failures": list(self.failures),
        }


class HardEvidenceGate:
    """Deterministic checks that semantic model judgment cannot override."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()

    def evaluate(self, contract: AcceptanceContract, bundle: EvidenceBundle) -> HardGateReport:
        results = [self._evaluate_criterion(criterion, bundle) for criterion in contract.criteria]
        failures = list(bundle.failures)
        if bundle.report_status != "success":
            failures.append(f"phase_report_status={bundle.report_status}")
        failures.extend(
            f"{result.criterion_id}: {result.reason}"
            for result in results
            if result.status == "failed"
        )
        return HardGateReport(passed=not failures, results=results, failures=failures)

    def _evaluate_criterion(self, criterion: GoalCriterion, bundle: EvidenceBundle) -> CriterionResult:
        if criterion.check_type == "file_exists":
            return self._file_result(criterion, bundle)
        if criterion.check_type == "command":
            return self._command_result(criterion, bundle)
        if criterion.check_type == "metric":
            return self._metric_result(criterion, bundle)
        return CriterionResult(criterion.id, "deferred", "requires semantic review")

    def _file_result(self, criterion: GoalCriterion, bundle: EvidenceBundle) -> CriterionResult:
        if not criterion.path:
            return CriterionResult(criterion.id, "failed", "required output path is not declared")
        target = (self.workspace / criterion.path).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            return CriterionResult(criterion.id, "failed", "required output escapes workspace")
        if not target.exists():
            return CriterionResult(criterion.id, "failed", f"missing required output: {criterion.path}")
        expected = self._normalize_path(criterion.path).rstrip("/")
        provenance = [
            artifact
            for artifact in bundle.artifacts
            if self._artifact_matches(expected, self._normalize_path(artifact))
        ]
        if not provenance:
            return CriterionResult(
                criterion.id,
                "failed",
                f"output exists but has no artifact provenance in this run: {criterion.path}",
            )
        return CriterionResult(
            criterion.id,
            "passed",
            "required output exists with run provenance",
            [f"artifact={item}" for item in provenance],
        )

    def _command_result(self, criterion: GoalCriterion, bundle: EvidenceBundle) -> CriterionResult:
        if not criterion.command:
            return CriterionResult(criterion.id, "failed", "required command is not declared")
        expected = self._normalize_command(criterion.command)
        matches = []
        for record in bundle.tool_records:
            if record.get("tool") not in ("test_runner", "shell_runner"):
                continue
            actual = self._normalize_command(record.get("arguments", {}).get("command", ""))
            if actual == expected and record.get("success") is True and record.get("exit_code") == 0:
                matches.append(record)
        if not matches:
            return CriterionResult(
                criterion.id,
                "failed",
                f"no successful exit-code-0 evidence for exact command: {criterion.command}",
            )
        return CriterionResult(
            criterion.id,
            "passed",
            "exact command completed with exit code 0",
            [f"command={criterion.command}", "exit_code=0"],
        )

    def _metric_result(self, criterion: GoalCriterion, bundle: EvidenceBundle) -> CriterionResult:
        if not criterion.metric_name or criterion.threshold is None:
            return CriterionResult(criterion.id, "deferred", "metric name or threshold requires semantic review")
        values = []
        for record in bundle.tool_records:
            metrics = record.get("metadata", {}).get("metrics", {})
            if criterion.metric_name in metrics:
                values.append(float(metrics[criterion.metric_name]))
        if not values or max(values) < criterion.threshold:
            return CriterionResult(
                criterion.id,
                "failed",
                f"metric {criterion.metric_name} did not reach {criterion.threshold}",
            )
        value = max(values)
        return CriterionResult(
            criterion.id,
            "passed",
            f"metric threshold reached: {value} >= {criterion.threshold}",
            [f"{criterion.metric_name}={value}"],
        )

    @staticmethod
    def _normalize_path(value: str) -> str:
        return value.replace("\\", "/").lstrip("./")

    @staticmethod
    def _artifact_matches(expected: str, artifact: str) -> bool:
        normalized = artifact.rstrip("/")
        return normalized == expected or normalized.startswith(expected + "/")

    @staticmethod
    def _normalize_command(value: str) -> str:
        return " ".join(str(value).split()).strip().lower()
