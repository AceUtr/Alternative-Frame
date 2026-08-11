from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.routing import NodeRouter, TaskRequirements

from . import (
    ExecutionNode,
    NodeExecutionError,
    NodeExecutionTimeout,
    NodeNetworkError,
    NodeUnavailableError,
)


RuntimeEventCallback = Callable[[str, Dict[str, Any]], None]


@dataclass
class RuntimeExecutionResult:
    success: bool
    output: Any = None
    error: str = ""
    selected_node: Optional[ExecutionNode] = None
    fallback_count: int = 0
    tool_records: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def deployment_target(self) -> Optional[str]:
        return self.selected_node.node_type if self.selected_node else None

    @property
    def selected_node_id(self) -> Optional[str]:
        return self.selected_node.node_id if self.selected_node else None


class RuntimeExecutor:
    """Execute a task on a routed node and fall back across eligible nodes.

    All nodes are local in v0.1.  The action receives the chosen node, which
    makes deterministic fault injection and future remote adapters explicit.
    """

    def __init__(
        self,
        router: NodeRouter | None = None,
        on_event: RuntimeEventCallback | None = None,
    ) -> None:
        self.router = router or NodeRouter()
        self.on_event = on_event

    def execute(
        self,
        requirements: TaskRequirements,
        nodes: Iterable[ExecutionNode],
        action: Callable[[ExecutionNode], Any],
    ) -> RuntimeExecutionResult:
        node_list = list(nodes)
        node_map = {node.node_id: node for node in node_list}
        if len(node_map) != len(node_list):
            self._emit(
                "node_execution_failed",
                {
                    "task_id": requirements.task_id,
                    "failure_kind": "duplicate_node_id",
                    "error": "execution node ids must be unique",
                    "duration": 0.0,
                    "fallback_count": 0,
                },
            )
            return RuntimeExecutionResult(False, error="execution node ids must be unique")

        decision = self.router.route(requirements, node_list)
        placement = decision.to_dict()
        self._emit(
            "placement_decided",
            {
                "task_id": requirements.task_id,
                "privacy_level": requirements.privacy_level,
                "required_capabilities": sorted(requirements.required_capabilities),
                **placement,
            },
        )
        if decision.selected_node is None:
            no_eligible_record = {
                "schema_version": "1.0",
                "tool": "runtime_executor",
                "call_type": "node_execution",
                "task_id": requirements.task_id,
                "success": False,
                "node": None,
                "node_id": None,
                "node_type": None,
                "deployment_target": None,
                "placement_reason": placement.get("placement_reason", ""),
                "actual_duration_ms": 0.0,
                "duration": 0.0,
                "duration_seconds": 0.0,
                "fallback_count": 0,
                "failure_kind": "no_eligible_node",
                "error": "no eligible execution node",
                "metadata": {
                    "deployment_target": None,
                    "privacy_level": requirements.privacy_level,
                    "placement": placement,
                },
            }
            self._emit(
                "node_execution_failed",
                self._event_from_record(no_eligible_record),
            )
            return RuntimeExecutionResult(
                False,
                error="no eligible execution node",
                tool_records=[no_eligible_record],
            )

        candidate_ids = list(decision.ranked_node_ids)
        if not requirements.allow_fallback:
            candidate_ids = candidate_ids[:1]

        records: List[Dict[str, Any]] = []
        last_error = "execution did not start"
        previous_node: ExecutionNode | None = None
        for attempt_index, node_id in enumerate(candidate_ids):
            node = node_map[node_id]
            node_reason = self._placement_reason(placement, node, attempt_index)
            if attempt_index and previous_node is not None:
                self._emit(
                    "node_fallback_started",
                    {
                        "task_id": requirements.task_id,
                        "from_node_id": previous_node.node_id,
                        "from_node_type": previous_node.node_type,
                        "node_id": node.node_id,
                        "node_type": node.node_type,
                        "placement_reason": node_reason,
                        "fallback_count": attempt_index,
                        "previous_error": last_error,
                    },
                )
            self._emit(
                "node_execution_started",
                {
                    "task_id": requirements.task_id,
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "placement_reason": node_reason,
                    "estimated_latency_ms": node.estimated_latency_ms,
                    "estimated_cost": node.estimated_cost,
                    "fallback_count": attempt_index,
                },
            )
            started = time.perf_counter()
            try:
                output = node.execute(lambda: action(node))
                duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
                record = self._record(
                    requirements,
                    placement,
                    node,
                    attempt_index,
                    True,
                    duration_ms,
                    output=output,
                )
                records.append(record)
                self._emit(
                    "node_execution_completed",
                    self._event_from_record(record),
                )
                return RuntimeExecutionResult(
                    True,
                    output=output,
                    selected_node=node,
                    fallback_count=attempt_index,
                    tool_records=records,
                )
            except NodeExecutionError as exc:
                duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
                last_error = f"{type(exc).__name__}: {exc}"
                record = self._record(
                    requirements,
                    placement,
                    node,
                    attempt_index,
                    False,
                    duration_ms,
                    error=last_error,
                    failure_kind=self._failure_kind(exc),
                )
                records.append(record)
                self._emit("node_execution_failed", self._event_from_record(record))
                previous_node = node
            except Exception as exc:
                # An Agent or Tool failure is not a node-placement failure.
                # Stopping here avoids repeating a potentially non-idempotent
                # task on another node; the Orchestrator owns task retries.
                duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
                last_error = f"{type(exc).__name__}: {exc}"
                record = self._record(
                    requirements,
                    placement,
                    node,
                    attempt_index,
                    False,
                    duration_ms,
                    error=last_error,
                    failure_kind="agent_or_tool_error",
                )
                records.append(record)
                self._emit("node_execution_failed", self._event_from_record(record))
                return RuntimeExecutionResult(
                    False,
                    error=last_error,
                    selected_node=node,
                    fallback_count=attempt_index,
                    tool_records=records,
                )

        return RuntimeExecutionResult(
            False,
            error=last_error,
            selected_node=records and node_map[records[-1]["node_id"]] or None,
            fallback_count=max(len(records) - 1, 0),
            tool_records=records,
        )

    @staticmethod
    def _record(
        requirements: TaskRequirements,
        placement: Dict[str, Any],
        node: ExecutionNode,
        fallback_count: int,
        success: bool,
        duration_ms: float,
        output: Any = None,
        error: str = "",
        failure_kind: str = "",
    ) -> Dict[str, Any]:
        reason = RuntimeExecutor._placement_reason(placement, node, fallback_count)
        duration_seconds = round(duration_ms / 1000.0, 6)
        return {
            "schema_version": "1.0",
            "tool": "runtime_executor",
            "call_type": "node_execution",
            "task_id": requirements.task_id,
            "success": success,
            "node": node.node_type,
            "node_id": node.node_id,
            "node_type": node.node_type,
            "deployment_target": node.node_type,
            "placement_reason": reason,
            "estimated_latency_ms": node.estimated_latency_ms,
            "estimated_cost": node.estimated_cost,
            "actual_duration_ms": duration_ms,
            "duration": duration_seconds,
            "duration_seconds": duration_seconds,
            "fallback_count": fallback_count,
            "output_excerpt": str(output)[:500] if output is not None else "",
            "error": error,
            "failure_kind": failure_kind,
            "metadata": {
                "deployment_target": node.node_type,
                "privacy_level": requirements.privacy_level,
                "placement": placement,
            },
        }

    @staticmethod
    def _placement_reason(
        placement: Dict[str, Any],
        node: ExecutionNode,
        fallback_count: int,
    ) -> str:
        node_reasons = placement.get("candidate_reasons", {}).get(node.node_id, [])
        reason = "; ".join(node_reasons) or placement.get("placement_reason", "")
        if fallback_count:
            reason = f"fallback candidate after {fallback_count} failed attempt(s); {reason}"
        return reason

    @staticmethod
    def _failure_kind(exc: NodeExecutionError) -> str:
        if isinstance(exc, NodeExecutionTimeout):
            return "timeout"
        if isinstance(exc, NodeNetworkError):
            return "network_interrupted"
        if isinstance(exc, NodeUnavailableError):
            return "node_offline"
        return "node_execution_error"

    @staticmethod
    def _event_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: record.get(key)
            for key in (
                "task_id",
                "node_id",
                "node_type",
                "placement_reason",
                "duration",
                "actual_duration_ms",
                "fallback_count",
                "success",
                "failure_kind",
                "error",
            )
        }

    def _emit(self, event: str, payload: Dict[str, Any]) -> None:
        if not self.on_event:
            return
        try:
            self.on_event(event, payload)
        except Exception:
            # Observability must never change task execution semantics.
            pass
