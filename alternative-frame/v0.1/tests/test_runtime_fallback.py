import unittest

from core.agents import Agent, AgentRegistry, DeterministicAgent
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator
from core.routing import TaskRequirements
from core.runtime_nodes import (
    CloudNode,
    DeviceNode,
    EdgeNode,
    NodeExecutionError,
    NodeRoutedAgent,
    RuntimeExecutor,
)


class RuntimeFallbackTests(unittest.TestCase):
    def setUp(self):
        self.executor = RuntimeExecutor()

    def test_cloud_failure_falls_back_to_edge_and_records_chain(self):
        nodes = [
            DeviceNode("device-1", {"compute"}, estimated_latency_ms=70),
            EdgeNode("edge-1", {"compute"}, estimated_latency_ms=20),
            CloudNode("cloud-1", {"compute"}, estimated_latency_ms=8),
        ]

        def action(node):
            if node.node_type == "cloud":
                raise NodeExecutionError("injected cloud outage")
            return f"completed on {node.node_id}"

        result = self.executor.execute(
            TaskRequirements(
                task_id="heavy-compute",
                required_capabilities={"compute"},
                preferred_tier="cloud",
            ),
            nodes,
            action,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.selected_node.node_type, "edge")
        self.assertEqual(result.fallback_count, 1)
        self.assertEqual([record["node_type"] for record in result.tool_records], ["cloud", "edge"])
        self.assertFalse(result.tool_records[0]["success"])
        self.assertTrue(result.tool_records[1]["success"])
        self.assertIn("injected cloud outage", result.tool_records[0]["error"])

    def test_sensitive_task_fallback_remains_on_device(self):
        nodes = [
            DeviceNode("device-a", {"private_compute"}, estimated_latency_ms=5),
            DeviceNode("device-b", {"private_compute"}, estimated_latency_ms=10),
            EdgeNode("edge-1", {"private_compute"}, estimated_latency_ms=1),
            CloudNode("cloud-1", {"private_compute"}, estimated_latency_ms=1),
        ]

        def action(node):
            if node.node_id == "device-a":
                raise NodeExecutionError("injected device-a failure")
            return node.node_id

        result = self.executor.execute(
            TaskRequirements(
                task_id="private-task",
                privacy_level="sensitive",
                required_capabilities={"private_compute"},
            ),
            nodes,
            action,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.selected_node_id, "device-b")
        self.assertTrue(all(record["node_type"] == "device" for record in result.tool_records))

    def test_fallback_can_be_disabled(self):
        nodes = [
            EdgeNode("edge-1", {"compute"}, estimated_latency_ms=20),
            CloudNode("cloud-1", {"compute"}, estimated_latency_ms=5),
        ]

        def always_fails(_node):
            raise NodeExecutionError("injected failure")

        result = self.executor.execute(
            TaskRequirements(
                task_id="no-fallback",
                required_capabilities={"compute"},
                preferred_tier="cloud",
                allow_fallback=False,
            ),
            nodes,
            always_fails,
        )

        self.assertFalse(result.success)
        self.assertEqual(len(result.tool_records), 1)
        self.assertEqual(result.tool_records[0]["node_type"], "cloud")

    def test_orchestrator_runs_existing_agent_through_node_wrapper(self):
        registry = AgentRegistry()
        registry.register(
            NodeRoutedAgent(
                DeterministicAgent("worker"),
                [
                    DeviceNode("device-1", {"private_file"}),
                    EdgeNode("edge-1", {"private_file"}),
                ],
            )
        )
        plan = Plan(
            "process a private file",
            [
                SubTask(
                    "private-task",
                    "worker",
                    "process private input",
                    max_retries=0,
                    metadata={
                        "privacy_level": "sensitive",
                        "required_capabilities": ["private_file"],
                    },
                )
            ],
        )

        report = Orchestrator(registry).run(plan)
        result = report.results["private-task"]

        self.assertEqual(report.status, "success")
        self.assertEqual(result.tool_records[0]["node_type"], "device")
        self.assertIn("deployment_target=device", result.evidence)

    def test_agent_error_does_not_trigger_cross_node_fallback(self):
        class RaisingAgent(Agent):
            role = "worker"

            def run(self, task, context):
                raise ValueError("agent logic failed")

        registry = AgentRegistry()
        registry.register(
            NodeRoutedAgent(
                RaisingAgent(),
                [
                    CloudNode("cloud-1", {"compute"}, estimated_latency_ms=5),
                    EdgeNode("edge-1", {"compute"}, estimated_latency_ms=20),
                ],
            )
        )
        plan = Plan(
            "do work",
            [
                SubTask(
                    "work",
                    "worker",
                    "fail inside agent",
                    max_retries=0,
                    metadata={
                        "required_capabilities": ["compute"],
                        "preferred_tier": "cloud",
                    },
                )
            ],
        )

        report = Orchestrator(registry).run(plan)

        self.assertEqual(report.status, "failed")
        records = report.results["work"].tool_records
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["node_type"], "cloud")


if __name__ == "__main__":
    unittest.main()
