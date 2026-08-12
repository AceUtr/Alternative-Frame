from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from . import ExecutionNode


NODE_STATE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class NodeProbeResult:
    online: bool | None
    network_available: bool | None
    status: str = "success"

    def __post_init__(self) -> None:
        if self.status not in {"success", "failed", "unknown"}:
            raise ValueError(f"unsupported probe status: {self.status}")


NodeProbe = Callable[[ExecutionNode], NodeProbeResult]
NodeStateEventCallback = Callable[[str, dict], None]


class NodeStateStore:
    """Audit historical health and use a fresh probe for resumed routing."""

    def __init__(
        self,
        path: str | Path,
        run_id: str = "",
        probe: NodeProbe | None = None,
        on_event: NodeStateEventCallback | None = None,
    ) -> None:
        self.path = Path(path).resolve()
        self.run_id = run_id
        self.probe = probe
        self.on_event = on_event
        self._prepared = False

    def save(self, nodes: Iterable[ExecutionNode]) -> Path:
        node_list = sorted(nodes, key=lambda item: item.node_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": NODE_STATE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "nodes": [self._node_row(node) for node in node_list],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        for node in node_list:
            self._emit(
                "node_state_snapshot_saved",
                node,
                previous=None,
                probe_status=node.probe_status,
            )
        return self.path

    def prepare(self, nodes: Iterable[ExecutionNode]) -> list[ExecutionNode]:
        """Prepare nodes once per process; resume uses probe, never history, for routing."""
        node_list = list(nodes)
        if self._prepared:
            return node_list
        self._prepared = True
        if not self.path.is_file():
            self.save(node_list)
            return node_list

        previous = self._load_rows()
        for node in node_list:
            old = previous.get(node.node_id)
            if old and old.get("node_type") != node.node_type:
                raise ValueError(f"node type changed for {node.node_id}")
            result = self._probe(node)
            node.probe_status = result.status
            if result.status == "success" and result.online is not None:
                node.online = result.online
                node.network_available = bool(result.network_available)
            else:
                # Unknown health is not eligible for routing.
                node.online = False
                node.network_available = False
            self._emit("node_state_reprobed", node, old, node.probe_status)
            if old and self._changed(old, node):
                self._emit("node_state_changed", node, old, node.probe_status)
        self.save(node_list)
        return node_list

    def restore(self, nodes: Iterable[ExecutionNode]) -> list[ExecutionNode]:
        """Backward-compatible alias; historical values never override current probes."""
        return self.prepare(nodes)

    def _probe(self, node: ExecutionNode) -> NodeProbeResult:
        if not self.probe:
            return NodeProbeResult(None, None, "unknown")
        try:
            result = self.probe(node)
            if not isinstance(result, NodeProbeResult):
                raise TypeError("node probe must return NodeProbeResult")
            return result
        except Exception:
            return NodeProbeResult(None, None, "failed")

    def _load_rows(self) -> dict[str, dict]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != NODE_STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported node state schema: {payload.get('schema_version')}")
        return {str(row.get("node_id")): row for row in payload.get("nodes", [])}

    @staticmethod
    def _node_row(node: ExecutionNode) -> dict:
        return {
            "node_id": node.node_id,
            "node_type": node.node_type,
            "online": node.online,
            "network_available": node.network_available,
            "probe_status": node.probe_status,
        }

    @staticmethod
    def _changed(previous: dict, node: ExecutionNode) -> bool:
        return (
            bool(previous.get("online")) != node.online
            or bool(previous.get("network_available")) != node.network_available
        )

    def _emit(self, event: str, node: ExecutionNode, previous: dict | None, probe_status: str) -> None:
        if not self.on_event:
            return
        payload = {
            "run_id": self.run_id,
            "node_id": node.node_id,
            "node_type": node.node_type,
            "previous_online": previous.get("online") if previous else None,
            "current_online": node.online,
            "previous_network_available": previous.get("network_available") if previous else None,
            "current_network_available": node.network_available,
            "probe_status": probe_status,
        }
        try:
            self.on_event(event, payload)
        except Exception:
            pass


__all__ = ["NODE_STATE_SCHEMA_VERSION", "NodeProbeResult", "NodeStateStore"]
