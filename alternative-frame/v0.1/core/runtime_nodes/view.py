from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping

from . import ExecutionNode
from .telemetry import aggregate_runtime_metrics


@dataclass(frozen=True)
class NodeView:
    node_id: str
    node_type: str
    online: bool
    network_available: bool
    capabilities: List[str]
    estimated_latency_ms: float
    estimated_cost: float
    health: str

    @classmethod
    def from_node(cls, node: ExecutionNode) -> "NodeView":
        health = "offline" if not node.online else "network_unavailable" if not node.network_available else "healthy"
        return cls(
            node_id=node.node_id,
            node_type=node.node_type,
            online=node.online,
            network_available=node.network_available,
            capabilities=sorted(node.capabilities),
            estimated_latency_ms=node.estimated_latency_ms,
            estimated_cost=node.estimated_cost,
            health=health,
        )


@dataclass(frozen=True)
class RouteEventView:
    event: str
    task_id: str
    node_id: str | None = None
    node_type: str | None = None
    placement_reason: str = ""
    duration: float = 0.0
    fallback_count: int = 0
    success: bool | None = None
    failure_kind: str = ""
    error: str = ""
    time: str = ""

    @classmethod
    def from_event(cls, record: Mapping[str, Any]) -> "RouteEventView":
        payload = record.get("payload", {}) if isinstance(record.get("payload", {}), Mapping) else {}
        return cls(
            event=str(record.get("event") or ""),
            task_id=str(payload.get("task_id") or ""),
            node_id=payload.get("node_id"),
            node_type=payload.get("node_type"),
            placement_reason=str(payload.get("placement_reason") or ""),
            duration=float(payload.get("duration") or 0.0),
            fallback_count=int(payload.get("fallback_count") or 0),
            success=payload.get("success") if isinstance(payload.get("success"), bool) else None,
            failure_kind=str(payload.get("failure_kind") or ""),
            error=str(payload.get("error") or ""),
            time=str(record.get("time") or ""),
        )


@dataclass
class RuntimeViewSnapshot:
    schema_version: str = "1.0"
    run_id: str = ""
    nodes: List[NodeView] = field(default_factory=list)
    route_events: List[RouteEventView] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "nodes": [asdict(node) for node in self.nodes],
            "route_events": [asdict(event) for event in self.route_events],
            "metrics": dict(self.metrics),
        }


def build_runtime_view(
    nodes: Iterable[ExecutionNode],
    evidence_records: Iterable[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]],
    run_id: str = "",
) -> RuntimeViewSnapshot:
    records = [dict(record) for record in evidence_records]
    route_events = [
        RouteEventView.from_event(record)
        for record in events
        if str(record.get("event") or "").startswith(("placement_", "node_"))
    ]
    return RuntimeViewSnapshot(
        run_id=run_id,
        nodes=[NodeView.from_node(node) for node in sorted(nodes, key=lambda item: item.node_id)],
        route_events=route_events,
        metrics=aggregate_runtime_metrics(records),
    )


__all__ = [
    "NodeView",
    "RouteEventView",
    "RuntimeViewSnapshot",
    "build_runtime_view",
]
