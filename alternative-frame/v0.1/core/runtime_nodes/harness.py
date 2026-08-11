from __future__ import annotations

from typing import Callable, Iterable, Mapping

from core.agents import Agent
from core.models import AgentResult, SubTask
from core.routing import TaskRequirements

from . import ExecutionNode
from .executor import RuntimeExecutor


NodeProvider = Iterable[ExecutionNode] | Callable[[SubTask], Iterable[ExecutionNode]]


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
    ) -> None:
        if not getattr(delegate, "role", None):
            raise ValueError("delegate Agent must define a role")
        self.delegate = delegate
        self.role = delegate.role
        self.nodes = nodes
        self.executor = executor or RuntimeExecutor()

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

        runtime_result = self.executor.execute(
            requirements,
            available_nodes,
            run_delegate,
        )
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


__all__ = ["NodeRoutedAgent"]
