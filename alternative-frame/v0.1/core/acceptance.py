from __future__ import annotations

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
    """
    Evaluate structured evidence instead of trusting model prose.
    """

    def __init__(
        self,
        workspace: str | Path | None = None,
        execute_commands: bool = False
    ):
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.execute_commands = execute_commands


    def evaluate(
        self,
        task: SubTask,
        result: AgentResult
    ) -> AcceptanceReport:

        checks = task.metadata.get("checks", [])

        if not checks:
            return AcceptanceReport(
                result.status == "success",
                ["no_checks_declared"]
                if result.status == "success"
                else [],
                result.failures
            )


        passed = []
        failures = []

        content = (result.summary or "").lower()


        for check in checks:

            check_id = check.get("id", "unknown")
            check_type = check.get("check_type", "manual")


            # ============================
            # command check
            # ============================

            if check_type == "command":

                command = check.get("command")

                expected = self._normalize_command(command)


                matching_records = [

                    record

                    for record in result.tool_records

                    if (

                        record.get("tool")
                        in (
                            "test_runner",
                            "shell_runner"
                        )

                        and

                        self._normalize_command(
                            record.get("arguments", {}).get("command")
                            or
                            record.get("metadata", {}).get("command")
                        )
                        == expected

                        and

                        record.get(
                            "success"
                        )
                        is True

                        and

                        record.get(
                            "exit_code"
                        )
                        == 0
                    )
                ]


                if matching_records:

                    passed.append(
                        f"{check_id}: exact_command_exit_code=0"
                    )


                elif not self.execute_commands:

                    failures.append(
                        f"{check_id}: exact_command_evidence_missing ({command})"
                    )


                else:

                    ok, detail = self._run_command(
                        command
                    )

                    if ok:
                        passed.append(
                            f"{check_id}: {detail}"
                        )
                    else:
                        failures.append(
                            f"{check_id}: {detail}"
                        )



            # ============================
            # file check
            # ============================

            elif check_type == "file_exists":

                expected = (

                    [check["path"]]

                    if check.get("path")

                    else task.metadata.get(
                        "expected_outputs",
                        []
                    )
                )


                missing = [

                    p

                    for p in expected

                    if not (
                        self.workspace / p
                    ).exists()

                ]


                if missing:

                    failures.append(
                        f"{check_id}: missing_artifacts={missing}"
                    )


                else:

                    recorded = {

                        self._normalize_path(path)

                        for path in result.artifacts

                    }


                    for record in result.tool_records:

                        if record.get("success"):

                            recorded.update(

                                self._normalize_path(path)

                                for path in record.get(
                                    "metadata",
                                    {}
                                ).get(
                                    "artifacts",
                                    []
                                )

                            )


                    missing_provenance = [

                        path

                        for path in expected

                        if not self._has_artifact_provenance(
                            path,
                            recorded
                        )

                    ]


                    if missing_provenance:

                        failures.append(
                            f"{check_id}: missing_run_provenance={missing_provenance}"
                        )

                    else:

                        passed.append(
                            f"{check_id}: artifacts_exist_with_run_provenance"
                        )



            # ============================
            # metric check
            # ============================

            elif check_type == "metric":

                tokens = (

                    "metric",
                    "指标",
                    "experiment",
                    "实验",
                    "baseline",
                    "基线"

                )


                if any(
                    token in content
                    for token in tokens
                ):

                    passed.append(
                        f"{check_id}: evidence_present"
                    )

                else:

                    failures.append(
                        f"{check_id}: metric_evidence_missing"
                    )



            # ============================
            # manual check
            # ============================

            else:

                evidence_words = (

                    "通过",
                    "passed",
                    "verified",
                    "evidence",
                    "证据"

                )


                if any(
                    word in content
                    for word in evidence_words
                ):

                    passed.append(
                        f"{check_id}: textual_evidence_present"
                    )

                else:

                    failures.append(
                        f"{check_id}: evidence_missing"
                    )


        return AcceptanceReport(

            not failures
            and result.status == "success",

            passed,

            failures

        )



    @staticmethod
    def _normalize_command(command):

        """
        Normalize shell commands.

        Example:

        pytest D:/xxx/software_task/tests/test_app.py -v

        becomes:

        pytest tests/test_app.py -v
        """

        cmd = (
            " ".join(
                str(command or "").split()
            )
            .strip()
            .lower()
        )


        cmd = cmd.replace(
            "\\",
            "/"
        )


        if "pytest" in cmd:

            parts = cmd.split()

            normalized_parts = []


            for part in parts:


                if "/tests/" in part:

                    index = part.find(
                        "/tests/"
                    )

                    part = (
                        "tests/"
                        +
                        part[
                            index + len("/tests/"):
                        ]
                    )


                normalized_parts.append(
                    part
                )


            cmd = " ".join(
                normalized_parts
            )


        return cmd



    @staticmethod
    def _normalize_path(path):

        return (
            str(path or "")
            .replace("\\", "/")
            .strip()
            .rstrip("/")
        )



    @classmethod
    def _has_artifact_provenance(
        cls,
        expected,
        recorded
    ):

        normalized = cls._normalize_path(
            expected
        )


        if normalized in recorded:

            return True


        return any(

            artifact.startswith(
                normalized + "/"
            )

            for artifact in recorded

        )



    def _run_command(
        self,
        command: str
    ):

        try:

            completed = subprocess.run(

                command,

                cwd=self.workspace,

                shell=True,

                capture_output=True,

                text=True,

                timeout=120

            )


            detail = (
                f"exit_code={completed.returncode}"
            )


            return (
                completed.returncode == 0,
                detail
            )


        except Exception as exc:


            return (
                False,
                f"command_error={exc}"
            )
