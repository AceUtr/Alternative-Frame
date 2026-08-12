from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from . import ExecutionNode


NODE_STATE_SCHEMA_VERSION = "1.0"


class NodeStateStore:
    """Persist mutable node health beside a long-horizon run.

    This sidecar deliberately avoids adding fields to the frozen
    ``LongHorizonState`` model. Static node capabilities remain configuration;
    only health that may change at runtime is restored.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    def save(self, nodes: Iterable[ExecutionNode]) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": NODE_STATE_SCHEMA_VERSION,
            "nodes": [
                {
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "online": node.online,
                    "network_available": node.network_available,
                }
                for node in sorted(nodes, key=lambda item: item.node_id)
            ],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        return self.path

    def restore(self, nodes: Iterable[ExecutionNode]) -> list[ExecutionNode]:
        node_list = list(nodes)
        if not self.path.is_file():
            self.save(node_list)
            return node_list
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != NODE_STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported node state schema: {payload.get('schema_version')}")
        saved = {str(row.get("node_id")): row for row in payload.get("nodes", [])}
        for node in node_list:
            row = saved.get(node.node_id)
            if not row:
                continue
            if row.get("node_type") != node.node_type:
                raise ValueError(f"node type changed for {node.node_id}")
            node.online = bool(row.get("online", False))
            node.network_available = bool(row.get("network_available", False))
        return node_list


__all__ = ["NODE_STATE_SCHEMA_VERSION", "NodeStateStore"]
