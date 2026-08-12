from __future__ import annotations

import subprocess
import sys
import time
import os
from pathlib import Path
from typing import Any, Dict

from core.tools.base import Tool, ToolResult


class SoftwareShellRunner(Tool):
    """Software-domain shell runner with deterministic Python resolution."""

    name = "shell_runner"

    def __init__(self, workspace: str | Path, timeout_seconds: int = 120, max_output: int = 12000):
        self.workspace = Path(workspace).resolve()
        self.timeout_seconds = timeout_seconds
        self.max_output = max_output

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Run a software task command inside the fixture workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        }

    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        command = arguments.get("command", "")
        if not command:
            return ToolResult(self.name, False, error="command is empty")
        if any(token in command.lower() for token in ("format c:", "rm -rf /", "del /s /q c:\\", "shutdown")):
            return ToolResult(self.name, False, error="blocked dangerous command")

        runtime_command = self._with_current_python(command)
        started = time.perf_counter()
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            completed = subprocess.run(
                runtime_command,
                cwd=self.workspace,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult(
                self.name,
                False,
                error=f"timeout after {self.timeout_seconds}s",
                output=str(exc),
                duration_seconds=round(time.perf_counter() - started, 3),
                metadata={"command": command, "runtime_command": runtime_command},
            )

        output = (completed.stdout + ("\n" + completed.stderr if completed.stderr else ""))[: self.max_output]
        return ToolResult(
            self.name,
            completed.returncode == 0,
            output=output,
            exit_code=completed.returncode,
            duration_seconds=round(time.perf_counter() - started, 3),
            metadata={"command": command, "runtime_command": runtime_command},
        )

    @staticmethod
    def _with_current_python(command: str) -> str:
        stripped = command.strip()
        lowered = stripped.lower()
        for prefix in ("python ", "python3 ", "py "):
            if lowered.startswith(prefix):
                return f'"{sys.executable}" {stripped[len(prefix):]}'
        return command
