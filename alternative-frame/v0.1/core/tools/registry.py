from __future__ import annotations

from typing import Any, Dict, Iterable

from .base import Tool, ToolResult


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()):
        self._tools = {tool.name: tool for tool in tools}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self):
        return [tool.schema() for tool in self._tools.values()]

    def names(self):
        return tuple(sorted(self._tools))

    def has(self, name: str) -> bool:
        return name in self._tools

    def execute(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(name, False, error=f"unknown tool: {name}")
        try:
            return tool.execute(arguments)
        except Exception as exc:
            return ToolResult(name, False, error=str(exc))
