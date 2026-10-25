from __future__ import annotations

import re
from typing import Any, Dict

from .base import Tool, ToolResult
from .shell_runner import ShellRunner


class ExperimentRunner(Tool):
    name = "experiment_runner"

    def __init__(self, shell: ShellRunner):
        self.shell = shell

    def schema(self) -> Dict[str, Any]:
        return {"type": "function", "function": {"name": "experiment_runner", "description": "Run a reproducible research experiment", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}

    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        result = self.shell.execute({"command": arguments.get("command", "")})
        result.tool = self.name
        result.metadata["command"] = arguments.get("command", "")
        metric_matches = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s*([0-9]+(?:\.[0-9]+)?)", result.output)
        result.metadata["metrics"] = {key: float(value) for key, value in metric_matches}
        return result
