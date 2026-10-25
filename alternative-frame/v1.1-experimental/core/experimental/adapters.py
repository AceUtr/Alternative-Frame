"""Small protocols for replacing external services without changing orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, Sequence


class ModelAdapter(Protocol):
    def complete(self, messages: Sequence[dict[str, Any]]) -> dict[str, Any]: ...


class ToolAdapter(Protocol):
    def invoke(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class MemoryAdapter(Protocol):
    def put(self, namespace: str, content: str, metadata: dict[str, Any] | None = None) -> str: ...
    def search(self, namespace: str, query: str, limit: int = 5) -> list[dict[str, Any]]: ...


class EventAdapter(Protocol):
    def emit(self, event: str, payload: dict[str, Any]) -> None: ...


class JsonlEventLog:
    """Append-only canonical event log, safe for concurrent threads in one process."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        entry = {"event": event, "payload": payload}
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


@dataclass
class AdapterBundle:
    model: ModelAdapter | None = None
    tools: ToolAdapter | None = None
    memory: MemoryAdapter | None = None
    events: EventAdapter | None = None
