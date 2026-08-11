from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.routing import NodeRouter, TaskRequirements

from . import ExecutionNode, NodeExecutionError


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

    def __init__(self, router: NodeRouter | None = None) -> None:
        self.router = router or NodeRouter()

    def execute(
        self,
        requirements: TaskRequirements,
        nodes: Iterable[ExecutionNode],
        action: Callable[[ExecutionNode], Any],
    ) -> RuntimeExecutionResult:
        node_list = list(nodes)
        node_map = {node.node_id: node for node in node_list}
        if len(node_map) != len(node_list):
            return RuntimeExecutionResult(False, error="execution node ids must be unique")

        decision = self.router.route(requirements, node_list)
        if decision.selected_node is None:
            return RuntimeExecutionResult(
                False,
                error="no eligible execution node",
                tool_records=[
                    {
                        "tool": "runtime_executor",
                        "success": False,
                        "task_id": requirements.task_id,
                        "placement": decision.to_dict(),
                        "error": "no eligible execution node",
                    }
                ],
            )

        candidate_ids = list(decision.ranked_node_ids)
        if not requirements.allow_fallback:
            candidate_ids = candidate_ids[:1]

        records: List[Dict[str, Any]] = []
        last_error = "execution did not start"
        for attempt_index, node_id in enumerate(candidate_ids):
            node = node_map[node_id]
            started = time.perf_counter()
            try:
                output = node.execute(lambda: action(node))
                duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
                records.append(
                    self._record(
                        requirements,
                        decision.to_dict(),
                        node,
                        attempt_index,
                        True,
                        duration_ms,
                        output=output,
                    )
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
                records.append(
                    self._record(
                        requirements,
                        decision.to_dict(),
                        node,
                        attempt_index,
                        False,
                        duration_ms,
                        error=last_error,
                    )
                )
            except Exception as exc:
                # An Agent or Tool failure is not a node-placement failure.
                # Stopping here avoids repeating a potentially non-idempotent
                # task on another node; the Orchestrator owns task retries.
                duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
                last_error = f"{type(exc).__name__}: {exc}"
                records.append(
                    self._record(
                        requirements,
                        decision.to_dict(),
                        node,
                        attempt_index,
                        False,
                        duration_ms,
                        error=last_error,
                    )
                )
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
    ) -> Dict[str, Any]:
        node_reasons = placement.get("candidate_reasons", {}).get(node.node_id, [])
        reason = "; ".join(node_reasons) or placement.get("placement_reason", "")
        if fallback_count:
            reason = f"fallback candidate after {fallback_count} failed attempt(s); {reason}"
        return {
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
            "duration_seconds": round(duration_ms / 1000.0, 6),
            "fallback_count": fallback_count,
            "output_excerpt": str(output)[:500] if output is not None else "",
            "error": error,
            "metadata": {
                "deployment_target": node.node_type,
                "privacy_level": requirements.privacy_level,
                "placement": placement,
            },
        }
