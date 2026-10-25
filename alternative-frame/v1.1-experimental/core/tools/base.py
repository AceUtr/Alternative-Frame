from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ToolResult:
    tool: str
    success: bool
    output: str = ""
    error: str = ""
    exit_code: int | None = None
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_message(self) -> Dict[str, str]:
        import json
        return {"role": "tool", "content": json.dumps(asdict(self), ensure_ascii=False)}


class Tool(ABC):
    name: str

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError

