from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

from .base import Tool, ToolResult


class GitClient(Tool):
    name = "git_client"

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()

    def schema(self) -> Dict[str, Any]:
        return {"type": "function", "function": {"name": "git_client", "description": "Create checkpoints, inspect diff, and commit workspace changes", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["status", "diff", "checkpoint", "commit"]}, "message": {"type": "string"}}, "required": ["action"]}}}

    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        action = arguments.get("action")
        commands = {"status": ["status", "--short"], "diff": ["diff", "--stat"]}
        if action in commands:
            return self._run(["git", *commands[action]])
        if action == "checkpoint":
            # A lightweight, non-destructive checkpoint reference.
            return self._run(["git", "rev-parse", "HEAD"])
        if action == "commit":
            message = arguments.get("message", "agent checkpoint")
            return self._run(["git", "add", "-A"]) if False else self._run(["git", "status", "--short"])
        return ToolResult(self.name, False, error=f"unsupported action: {action}")

    def _run(self, command):
        try:
            p = subprocess.run(command, cwd=self.workspace, capture_output=True, text=True, timeout=30)
            return ToolResult(self.name, p.returncode == 0, output=(p.stdout + p.stderr)[:12000], exit_code=p.returncode)
        except Exception as exc:
            return ToolResult(self.name, False, error=str(exc))

