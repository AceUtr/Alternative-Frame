from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .models import AgentResult, SubTask


@dataclass
class AcceptanceReport:
    passed: bool
    checks: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)


class AcceptanceEvaluator:
    """Evaluate structured evidence instead of trusting model prose."""

    def __init__(self, workspace: str | Path | None = None, execute_commands: bool = False):
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.execute_commands = execute_commands

    def evaluate(self, task: SubTask, result: AgentResult) -> AcceptanceReport:
        checks = task.metadata.get("checks", [])
        if not checks:
            return AcceptanceReport(result.status == "success", ["no_checks_declared"] if result.status == "success" else [], result.failures)
        passed, failures = [], []
        content = (result.summary or "").lower()
        for check in checks:
            check_id = check.get("id", "unknown")
            check_type = check.get("check_type", "manual")
            if check_type == "command":
                command = check.get("command")
                expected = self._normalize_command(command)
                matching_records = [
                    record
                    for record in result.tool_records
                    if record.get("tool") in ("test_runner", "shell_runner")
                    and self._normalize_command(record.get("arguments", {}).get("command")) == expected
                    and record.get("success") is True
                    and record.get("exit_code") == 0
                ]
                if matching_records:
                    passed.append(f"{check_id}: exact_command_exit_code=0")
                elif not self.execute_commands:
                    failures.append(f"{check_id}: exact_command_evidence_missing ({command})")
                else:
                    ok, detail = self._run_command(command)
                    (passed if ok else failures).append(f"{check_id}: {detail}")
            elif check_type == "file_exists":
                expected = [check["path"]] if check.get("path") else task.metadata.get("expected_outputs", [])
                missing = [p for p in expected if not (self.workspace / p).exists()]
                if missing:
                    failures.append(f"{check_id}: missing_artifacts={missing}")
                else:
                    recorded = {self._normalize_path(path) for path in result.artifacts}
                    for record in result.tool_records:
                        if record.get("success") is True:
                            recorded.update(
                                self._normalize_path(path)
                                for path in record.get("metadata", {}).get("artifacts", [])
                            )
                    missing_provenance = [
                        path for path in expected if not self._has_artifact_provenance(path, recorded)
                    ]
                    if missing_provenance:
                        failures.append(f"{check_id}: missing_run_provenance={missing_provenance}")
                    else:
                        passed.append(f"{check_id}: artifacts_exist_with_run_provenance")
            elif check_type == "metric":
                if any(token in content for token in ("metric", "指标", "experiment", "实验", "baseline", "基线")):
                    passed.append(f"{check_id}: evidence_present")
                else:
                    failures.append(f"{check_id}: metric_evidence_missing")
            else:
                # A model response is not enough for required checks. It must
                # explicitly contain evidence language before passing.
                evidence_words = ("通过", "passed", "verified", "evidence", "证据")
                if any(word in content for word in evidence_words):
                    passed.append(f"{check_id}: textual_evidence_present")
                else:
                    failures.append(f"{check_id}: evidence_missing")
        return AcceptanceReport(not failures and result.status == "success", passed, failures)

    @staticmethod
    def _normalize_command(command):
        return " ".join(str(command or "").split()).strip().lower()

    @staticmethod
    def _normalize_path(path):
        return str(path or "").replace("\\", "/").strip().rstrip("/")

    @classmethod
    def _has_artifact_provenance(cls, expected, recorded):
        normalized = cls._normalize_path(expected)
        if normalized in recorded:
            return True
        # Directory outputs such as tests/ are proven by any artifact written below them.
        return str(expected).replace("\\", "/").strip().endswith("/") and any(
            artifact.startswith(normalized + "/") for artifact in recorded
        )

    def _run_command(self, command: str):
        try:
            completed = subprocess.run(command, cwd=self.workspace, shell=True, capture_output=True, text=True, timeout=120)
            detail = f"exit_code={completed.returncode}"
            return completed.returncode == 0, detail
        except Exception as exc:
            return False, f"command_error={exc}"
