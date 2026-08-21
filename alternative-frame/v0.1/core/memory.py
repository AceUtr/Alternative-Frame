"""Small auditable three-layer memory and trajectory replay primitives."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class MemoryRecord:
    key: str
    value: Any
    source: str = "runtime"
    phase: int | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "source": self.source, "phase": self.phase, "tags": self.tags}


class ThreeLayerMemory:
    """Working, episodic and durable memory with explicit promotion."""
    def __init__(self, root: Path | None = None):
        self.working: dict[str, MemoryRecord] = {}
        self.episodic: list[MemoryRecord] = []
        self.durable: dict[str, MemoryRecord] = {}
        self.root = Path(root) if root else None

    def remember(self, key: str, value: Any, *, layer: str = "working", source: str = "runtime", phase: int | None = None, tags: Iterable[str] = ()) -> MemoryRecord:
        record = MemoryRecord(key, value, source, phase, list(tags))
        if layer == "working": self.working[key] = record
        elif layer == "episodic": self.episodic.append(record)
        elif layer == "durable": self.durable[key] = record
        else: raise ValueError("layer must be working, episodic or durable")
        return record

    def promote(self, key: str, *, from_layer: str = "working", to_layer: str = "durable") -> MemoryRecord:
        source = self.working if from_layer == "working" else self.durable
        if key not in source: raise KeyError(key)
        record = source[key]
        return self.remember(record.key, record.value, layer=to_layer, source=record.source, phase=record.phase, tags=record.tags)

    def snapshot(self) -> dict[str, Any]:
        return {"working": {k: v.to_dict() for k, v in self.working.items()}, "episodic": [v.to_dict() for v in self.episodic], "durable": {k: v.to_dict() for k, v in self.durable.items()}}

    def persist(self, path: Path | None = None) -> Path:
        target = Path(path or (self.root / "memory.json" if self.root else "memory.json"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Path) -> "ThreeLayerMemory":
        data = json.loads(Path(path).read_text(encoding="utf-8")); memory = cls(Path(path).parent)
        for layer in ("working", "durable"):
            for key, item in data.get(layer, {}).items(): memory.remember(key, item.get("value"), layer=layer, source=item.get("source", "replay"), phase=item.get("phase"), tags=item.get("tags", []))
        for item in data.get("episodic", []): memory.remember(item["key"], item.get("value"), layer="episodic", source=item.get("source", "replay"), phase=item.get("phase"), tags=item.get("tags", []))
        return memory


def replay_events(events_path: Path) -> list[dict[str, Any]]:
    """Read append-only event history in order for deterministic UI/audit replay."""
    return [json.loads(line) for line in Path(events_path).read_text(encoding="utf-8").splitlines() if line.strip()]

