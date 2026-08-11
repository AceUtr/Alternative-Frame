from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, FrozenSet


class NodeExecutionError(RuntimeError):
    """Raised when an execution node cannot run the requested action."""


class NodeUnavailableError(NodeExecutionError):
    """Raised when a node goes offline before or during execution."""


class NodeNetworkError(NodeExecutionError):
    """Raised when a node loses required network connectivity."""


class NodeExecutionTimeout(NodeExecutionError):
    """Raised by a node adapter when its execution deadline is exceeded."""


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
    execution_failure_mode: str | None = None

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
        if self.execution_failure_mode not in {None, "offline", "network", "timeout"}:
            raise ValueError(f"unsupported execution_failure_mode: {self.execution_failure_mode}")

    def execute(self, action: Callable[[], Any]) -> Any:
        """Execute a local action while preserving a remote-compatible seam."""
        if not self.online:
            raise NodeUnavailableError(f"node is offline: {self.node_id}")
        if self.execution_failure_mode == "offline":
            self.online = False
            raise NodeUnavailableError(f"node went offline during execution: {self.node_id}")
        if self.execution_failure_mode == "network":
            self.network_available = False
            raise NodeNetworkError(f"network interrupted during execution: {self.node_id}")
        if self.execution_failure_mode == "timeout":
            raise NodeExecutionTimeout(f"execution timed out on node: {self.node_id}")
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
        execution_failure_mode: str | None = None,
    ) -> None:
        super().__init__(
            node_id=node_id,
            node_type="device",
            capabilities=frozenset(capabilities),
            estimated_latency_ms=estimated_latency_ms,
            estimated_cost=estimated_cost,
            online=online,
            network_available=network_available,
            execution_failure_mode=execution_failure_mode,
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
        execution_failure_mode: str | None = None,
    ) -> None:
        super().__init__(
            node_id=node_id,
            node_type="edge",
            capabilities=frozenset(capabilities),
            estimated_latency_ms=estimated_latency_ms,
            estimated_cost=estimated_cost,
            online=online,
            network_available=network_available,
            execution_failure_mode=execution_failure_mode,
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
        execution_failure_mode: str | None = None,
    ) -> None:
        super().__init__(
            node_id=node_id,
            node_type="cloud",
            capabilities=frozenset(capabilities),
            estimated_latency_ms=estimated_latency_ms,
            estimated_cost=estimated_cost,
            online=online,
            network_available=network_available,
            execution_failure_mode=execution_failure_mode,
        )


__all__ = [
    "CloudNode",
    "DeviceNode",
    "EdgeNode",
    "ExecutionNode",
    "LongHorizonEventSink",
    "NodeExecutionError",
    "NodeExecutionTimeout",
    "NodeNetworkError",
    "NodeRoutedAgent",
    "NodeUnavailableError",
    "RuntimeExecutionResult",
    "RuntimeExecutor",
    "RUNTIME_EVENT_NAMES",
    "RUNTIME_TELEMETRY_SCHEMA_VERSION",
    "RuntimeViewSnapshot",
    "aggregate_runtime_metrics",
    "build_runtime_view",
]


# Imported last to avoid a circular import while core.routing imports
# ExecutionNode for placement decisions.
from .executor import RuntimeExecutionResult, RuntimeExecutor
from .harness import LongHorizonEventSink, NodeRoutedAgent
from .telemetry import (
    RUNTIME_EVENT_NAMES,
    RUNTIME_TELEMETRY_SCHEMA_VERSION,
    aggregate_runtime_metrics,
)
from .view import RuntimeViewSnapshot, build_runtime_view
