from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, FrozenSet


class NodeExecutionError(RuntimeError):
    """Raised when an execution node cannot run the requested action."""


@dataclass
class ExecutionNode:
    """Description of one device, edge, or cloud execution target.

    The first implementation deliberately keeps execution local.  A future
    HTTP/gRPC node can preserve this metadata contract and replace ``execute``.
    """

    node_id: str
    node_type: str
    capabilities: FrozenSet[str] = field(default_factory=frozenset)
    estimated_latency_ms: float = 0.0
    estimated_cost: float = 0.0
    online: bool = True
    network_available: bool = True

    def __post_init__(self) -> None:
        self.node_id = str(self.node_id).strip()
        self.node_type = str(self.node_type).strip().lower()
        self.capabilities = frozenset(str(item).strip() for item in self.capabilities if str(item).strip())
        if not self.node_id:
            raise ValueError("node_id cannot be empty")
        if self.node_type not in {"device", "edge", "cloud"}:
            raise ValueError(f"unsupported node_type: {self.node_type}")
        if self.estimated_latency_ms < 0:
            raise ValueError("estimated_latency_ms cannot be negative")
        if self.estimated_cost < 0:
            raise ValueError("estimated_cost cannot be negative")

    def execute(self, action: Callable[[], Any]) -> Any:
        """Execute a local action while preserving a remote-compatible seam."""
        if not self.online:
            raise NodeExecutionError(f"node is offline: {self.node_id}")
        return action()


class DeviceNode(ExecutionNode):
    def __init__(
        self,
        node_id: str,
        capabilities=(),
        estimated_latency_ms: float = 5.0,
        estimated_cost: float = 0.0,
        online: bool = True,
        network_available: bool = True,
    ) -> None:
        super().__init__(
            node_id=node_id,
            node_type="device",
            capabilities=frozenset(capabilities),
            estimated_latency_ms=estimated_latency_ms,
            estimated_cost=estimated_cost,
            online=online,
            network_available=network_available,
        )


class EdgeNode(ExecutionNode):
    def __init__(
        self,
        node_id: str,
        capabilities=(),
        estimated_latency_ms: float = 20.0,
        estimated_cost: float = 0.2,
        online: bool = True,
        network_available: bool = True,
    ) -> None:
        super().__init__(
            node_id=node_id,
            node_type="edge",
            capabilities=frozenset(capabilities),
            estimated_latency_ms=estimated_latency_ms,
            estimated_cost=estimated_cost,
            online=online,
            network_available=network_available,
        )


class CloudNode(ExecutionNode):
    def __init__(
        self,
        node_id: str,
        capabilities=(),
        estimated_latency_ms: float = 80.0,
        estimated_cost: float = 1.0,
        online: bool = True,
        network_available: bool = True,
    ) -> None:
        super().__init__(
            node_id=node_id,
            node_type="cloud",
            capabilities=frozenset(capabilities),
            estimated_latency_ms=estimated_latency_ms,
            estimated_cost=estimated_cost,
            online=online,
            network_available=network_available,
        )


__all__ = [
    "CloudNode",
    "DeviceNode",
    "EdgeNode",
    "ExecutionNode",
    "NodeExecutionError",
    "NodeRoutedAgent",
    "RuntimeExecutionResult",
    "RuntimeExecutor",
]


# Imported last to avoid a circular import while core.routing imports
# ExecutionNode for placement decisions.
from .executor import RuntimeExecutionResult, RuntimeExecutor
from .harness import NodeRoutedAgent
