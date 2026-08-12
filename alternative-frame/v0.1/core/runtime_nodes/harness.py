from __future__ import annotations

from threading import Lock
from typing import Callable, Iterable, Mapping

from core.agents import Agent
from core.models import AgentResult, SubTask
from core.routing import TaskRequirements

from . import ExecutionNode
from .executor import RuntimeExecutor
from .state_store import NodeStateStore


NodeProvider = Iterable[ExecutionNode] | Callable[[SubTask], Iterable[ExecutionNode]]


class LongHorizonEventSink:
    """Thread-safe bridge from runtime events to LongHorizonStore.events.jsonl."""

    def __init__(self, store, run_id: str) -> None:
        self.store = store
        self.run_id = run_id
        self._lock = Lock()

    def __call__(self, event: str, payload: dict) -> None:
        with self._lock:
            self.store.append_event(self.run_id, event, payload)


class NodeRoutedAgent(Agent):
    """Compatibility wrapper that adds placement without changing Orchestrator.

    The wrapped Agent still owns task logic.  This wrapper only converts the
    frozen ``SubTask.metadata`` extension fields into TaskRequirements, runs
    the delegate on an eligible node, and appends structured placement records.
    """

    def __init__(
        self,
        delegate: Agent,
        nodes: NodeProvider,
        executor: RuntimeExecutor | None = None,
        node_state_store: NodeStateStore | None = None,
    ) -> None:
        if not getattr(delegate, "role", None):
            raise ValueError("delegate Agent must define a role")
        self.delegate = delegate
        self.role = delegate.role
        self.nodes = nodes
        self.executor = executor or RuntimeExecutor()
        self.node_state_store = node_state_store
        self._node_state_lock = Lock()

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        requirements = TaskRequirements.from_metadata(task.id, task.metadata)
        available_nodes = list(self.nodes(task) if callable(self.nodes) else self.nodes)

        def run_delegate(node: ExecutionNode) -> AgentResult:
            # Orchestrator already passes an attempt-local deepcopy, so adding
            # placement metadata here cannot mutate the original Plan.
            task.metadata["deployment_target"] = node.node_type
            task.metadata["execution_node"] = node.node_type
            task.metadata["node_id"] = node.node_id
            return self.delegate.run(task, context)

        def execute_on_nodes():
            return self.executor.execute(requirements, available_nodes, run_delegate)

        if self.node_state_store:
            # Keep restore -> execute -> save atomic for parallel Orchestrator
            # tasks sharing the same mutable node-state sidecar.
            with self._node_state_lock:
                available_nodes = self.node_state_store.prepare(available_nodes)
                try:
                    runtime_result = execute_on_nodes()
                finally:
                    self.node_state_store.save(available_nodes)
        else:
            runtime_result = execute_on_nodes()
        if not runtime_result.success or not isinstance(runtime_result.output, AgentResult):
            return AgentResult(
                subtask_id=task.id,
                status="failed",
                summary="node-routed execution failed",
                evidence=["runtime_node_selection_failed"],
                tool_records=runtime_result.tool_records,
                failures=[f"runtime_execution_failed: {runtime_result.error}"],
            )

        result = runtime_result.output
        result.tool_records = runtime_result.tool_records + list(result.tool_records)
        result.evidence = list(
            dict.fromkeys(
                list(result.evidence)
                + [
                    f"deployment_target={runtime_result.deployment_target}",
                    f"node_id={runtime_result.selected_node_id}",
                    f"fallback_count={runtime_result.fallback_count}",
                ]
            )
        )
        return result


__all__ = ["LongHorizonEventSink", "NodeRoutedAgent"]
