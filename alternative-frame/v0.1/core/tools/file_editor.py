from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any, Dict

from .base import Tool, ToolResult


class FileEditor(Tool):
    name = "file_editor"

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()

    def _safe(self, path: str) -> Path:
        candidate = (self.workspace / path).resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise ValueError(f"path escapes workspace: {path}")
        return candidate

    def schema(self) -> Dict[str, Any]:
        return {"type": "function", "function": {"name": "file_editor", "description": "Read, write, or list files inside the workspace", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["read", "write", "list"]}, "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["action", "path"]}}}

    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        path = self._safe(arguments.get("path", "."))
        action = arguments.get("action")
        if action == "read":
            if not path.is_file():
                return ToolResult(self.name, False, error=f"file not found: {path}")
            return ToolResult(self.name, True, output=path.read_text(encoding="utf-8", errors="replace"))
        if action == "list":
            if not path.is_dir():
                return ToolResult(self.name, False, error=f"directory not found: {path}")
            return ToolResult(self.name, True, output="\n".join(str(p.relative_to(self.workspace)) for p in path.iterdir()))
        if action == "write":
            content = arguments.get("content")
            if not isinstance(content, str):
                return ToolResult(self.name, False, error="content must be a string")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(self.name, True, output=f"wrote {path.relative_to(self.workspace)}")
        return ToolResult(self.name, False, error=f"unsupported action: {action}")

