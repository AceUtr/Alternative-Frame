from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath

from .acceptance_contract import AcceptanceContract


class ContractValidationError(ValueError):
    pass


class ContractValidator:
    CRITERION_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    CHECK_TYPES = {"file_exists", "command", "metric", "semantic", "manual"}
    ALLOWED_COMMANDS = {
        "python",
        "python3",
        "py",
        "pytest",
        "npm",
        "pnpm",
        "yarn",
        "cargo",
        "go",
        "ruff",
        "mypy",
    }
    FORBIDDEN_COMMAND_FRAGMENTS = {
        "rm -rf",
        "del /s",
        "format ",
        "shutdown",
        "powershell",
        "cmd /c",
        "git reset --hard",
        "git clean",
        "remove-item",
    }

    def __init__(self, max_criteria: int = 40):
        if max_criteria < 1:
            raise ValueError("max_criteria must be positive")
        self.max_criteria = max_criteria

    def validate(self, contract: AcceptanceContract, expected_goal: str) -> AcceptanceContract:
        errors = []
        if contract.goal.strip() != expected_goal.strip():
            errors.append("contract goal must exactly match the original user goal")
        if not isinstance(contract.goal_summary, str) or not contract.goal_summary.strip():
            errors.append("goal_summary must be non-empty")
        if not contract.criteria:
            errors.append("contract must contain at least one criterion")
        if len(contract.criteria) > self.max_criteria:
            errors.append(f"contract exceeds maximum criterion count {self.max_criteria}")
        ids = [criterion.id for criterion in contract.criteria if isinstance(criterion.id, str)]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            errors.append(f"duplicate criterion ids: {duplicates}")
        if not any(criterion.required for criterion in contract.criteria):
            errors.append("contract must contain at least one required criterion")
        for criterion in contract.criteria:
            if not isinstance(criterion.id, str) or not self.CRITERION_ID.fullmatch(criterion.id):
                errors.append(f"invalid criterion id: {criterion.id!r}")
            if not isinstance(criterion.description, str) or not criterion.description.strip():
                errors.append(f"criterion {criterion.id} has an empty description")
            if not isinstance(criterion.required, bool):
                errors.append(f"criterion {criterion.id} required must be boolean")
            if criterion.check_type not in self.CHECK_TYPES:
                errors.append(f"criterion {criterion.id} has unsupported check type: {criterion.check_type}")
                continue
            if criterion.check_type == "file_exists":
                if not self._safe_relative_path(criterion.path):
                    errors.append(f"criterion {criterion.id} has unsafe or missing relative path")
            elif criterion.check_type == "command":
                command_error = self._command_error(criterion.command)
                if command_error:
                    errors.append(f"criterion {criterion.id}: {command_error}")
            elif criterion.check_type == "metric":
                if not isinstance(criterion.metric_name, str) or not criterion.metric_name.strip():
                    errors.append(f"criterion {criterion.id} metric requires metric_name")
                if not isinstance(criterion.threshold, (int, float)) or isinstance(criterion.threshold, bool):
                    errors.append(f"criterion {criterion.id} metric threshold must be numeric")
        if not isinstance(contract.constraints, list) or not all(
            isinstance(item, str) and item.strip() for item in contract.constraints
        ):
            errors.append("constraints must be a list of non-empty strings")
        if errors:
            raise ContractValidationError("; ".join(errors))
        return contract

    @staticmethod
    def _safe_relative_path(value) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        windows = PureWindowsPath(value)
        posix = PurePosixPath(value)
        return not windows.is_absolute() and not posix.is_absolute() and ".." not in windows.parts and ".." not in posix.parts

    def _command_error(self, command):
        if not isinstance(command, str) or not command.strip():
            return "command check requires a non-empty command"
        if any(token in command for token in ("\n", "\r", ";", "&&", "||", "|", ">", "<", "`")):
            return "command contains forbidden shell control syntax"
        lowered = command.strip().lower()
        if any(fragment in lowered for fragment in self.FORBIDDEN_COMMAND_FRAGMENTS):
            return "command contains a forbidden destructive operation"
        executable = lowered.split()[0].strip('"\'')
        if executable not in self.ALLOWED_COMMANDS:
            return f"command executable is not allowed: {executable}"
        if executable in {"npm", "pnpm", "yarn"}:
            parts = lowered.split()
            if len(parts) < 2 or parts[1] not in {"test", "run"}:
                return f"{executable} contract commands are limited to test/run"
        if executable == "cargo" and not lowered.startswith("cargo test"):
            return "cargo contract commands are limited to cargo test"
        if executable == "go" and not lowered.startswith("go test"):
            return "go contract commands are limited to go test"
        return None
