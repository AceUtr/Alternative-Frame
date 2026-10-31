import unittest

from core.routing import NodeRouter, TaskRequirements
from core.runtime_nodes import CloudNode, DeviceNode, EdgeNode


class NodeRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = NodeRouter()

    def test_sensitive_task_never_leaves_device(self):
        nodes = [
            DeviceNode("device-1", {"file_read"}, estimated_latency_ms=8),
            EdgeNode("edge-1", {"file_read"}, estimated_latency_ms=2),
            CloudNode("cloud-1", {"file_read"}, estimated_latency_ms=1),
        ]
        decision = self.router.route(
            TaskRequirements(
                task_id="private-file",
                privacy_level="sensitive",
                required_capabilities={"file_read"},
            ),
            nodes,
        )

        self.assertEqual(decision.selected_node_id, "device-1")
        self.assertIn("sensitive data must remain on device", decision.rejected_nodes["edge-1"])
        self.assertIn("sensitive data must remain on device", decision.rejected_nodes["cloud-1"])

    def test_required_capability_filters_nodes(self):
        nodes = [
            DeviceNode("device-1", {"cpu"}),
            EdgeNode("edge-1", {"cpu"}),
            CloudNode("cloud-1", {"cpu", "gpu"}),
        ]
        decision = self.router.route(
            TaskRequirements(required_capabilities={"gpu"}),
            nodes,
        )

        self.assertEqual(decision.selected_node_id, "cloud-1")
        self.assertIn("missing capabilities: gpu", decision.rejected_nodes["device-1"])

    def test_latency_limit_is_a_hard_constraint(self):
        nodes = [
            DeviceNode("device-1", {"inference"}, estimated_latency_ms=40),
            EdgeNode("edge-1", {"inference"}, estimated_latency_ms=12),
            CloudNode("cloud-1", {"inference"}, estimated_latency_ms=90),
        ]
        decision = self.router.route(
            TaskRequirements(required_capabilities={"inference"}, max_latency_ms=20),
            nodes,
        )

        self.assertEqual(decision.selected_node_id, "edge-1")
        self.assertIn("estimated latency 90ms exceeds limit 20ms", decision.rejected_nodes["cloud-1"])

    def test_cost_limit_excludes_expensive_node(self):
        nodes = [
            DeviceNode("device-1", {"cpu"}, estimated_cost=0.0),
            EdgeNode("edge-1", {"cpu"}, estimated_cost=0.3),
            CloudNode("cloud-1", {"cpu"}, estimated_cost=1.2),
        ]
        decision = self.router.route(
            TaskRequirements(required_capabilities={"cpu"}, max_cost=0.1),
            nodes,
        )

        self.assertEqual(decision.selected_node_id, "device-1")
        self.assertIn("estimated cost 1.2 exceeds limit 0.1", decision.rejected_nodes["cloud-1"])

    def test_offline_cloud_falls_back_to_edge(self):
        nodes = [
            DeviceNode("device-1", {"compute"}, estimated_latency_ms=50),
            EdgeNode("edge-1", {"compute"}, estimated_latency_ms=20),
            CloudNode("cloud-1", {"compute"}, estimated_latency_ms=5, online=False),
        ]
        decision = self.router.route(
            TaskRequirements(
                required_capabilities={"compute"},
                preferred_tier="cloud",
            ),
            nodes,
        )

        self.assertEqual(decision.selected_node_id, "edge-1")
        self.assertIn("node is offline", decision.rejected_nodes["cloud-1"])

    def test_network_requirement_rejects_disconnected_node(self):
        nodes = [
            EdgeNode("edge-1", {"fetch"}, network_available=False),
            CloudNode("cloud-1", {"fetch"}, network_available=True),
        ]
        decision = self.router.route(
            TaskRequirements(required_capabilities={"fetch"}, network_required=True),
            nodes,
        )

        self.assertEqual(decision.selected_node_id, "cloud-1")
        self.assertIn("required network is unavailable", decision.rejected_nodes["edge-1"])


if __name__ == "__main__":
    unittest.main()
