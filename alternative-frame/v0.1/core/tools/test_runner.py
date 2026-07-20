from __future__ import annotations

import re
from typing import Any, Dict

from .base import Tool, ToolResult
from .shell_runner import ShellRunner


class TestRunner(Tool):
    name = "test_runner"

    def __init__(self, shell: ShellRunner):
        self.shell = shell

    def schema(self) -> Dict[str, Any]:
        return {"type": "function", "function": {"name": "test_runner", "description": "Run project tests and return a structured result", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Optional test command"}}, "required": []}}}

    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        command = arguments.get("command", "pytest -q")
        result = self.shell.execute({"command": command})
        passed = result.success
        match = re.search(r"(\d+)\s+passed", result.output)
        failed = re.search(r"(\d+)\s+failed", result.output)
        result.metadata.update({"passed": passed, "passed_count": int(match.group(1)) if match else 0, "failed_count": int(failed.group(1)) if failed else (0 if passed else 1)})
        return result

