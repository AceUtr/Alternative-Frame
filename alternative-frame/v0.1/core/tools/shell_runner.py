from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Dict

from .base import Tool, ToolResult


class ShellRunner(Tool):
    name = "shell_runner"

    def __init__(self, workspace: str | Path, timeout_seconds: int = 120, max_output: int = 12000):
        self.workspace = Path(workspace).resolve()
        self.timeout_seconds = timeout_seconds
        self.max_output = max_output

    def schema(self) -> Dict[str, Any]:
        return {"type": "function", "function": {"name": "shell_runner", "description": "Run a command inside the workspace with timeout", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}

    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        command = arguments.get("command", "")
        if not command:
            return ToolResult(self.name, False, error="command is empty")
        if any(token in command.lower() for token in ("format c:", "rm -rf /", "del /s /q c:\\", "shutdown")):
            return ToolResult(self.name, False, error="blocked dangerous command")
        started = time.perf_counter()
        try:
            p = subprocess.run(command, cwd=self.workspace, shell=True, capture_output=True, text=True, timeout=self.timeout_seconds)
            output = (p.stdout + ("\n" + p.stderr if p.stderr else ""))[: self.max_output]
            return ToolResult(self.name, p.returncode == 0, output=output, exit_code=p.returncode, duration_seconds=round(time.perf_counter() - started, 3))
        except subprocess.TimeoutExpired as exc:
            return ToolResult(self.name, False, error=f"timeout after {self.timeout_seconds}s", output=str(exc), duration_seconds=round(time.perf_counter() - started, 3))

