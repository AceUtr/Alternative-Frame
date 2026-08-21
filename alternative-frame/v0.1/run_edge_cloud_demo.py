"""Deterministic single-machine device/edge/cloud routing demonstration."""

from __future__ import annotations

import json

from core.agents import AgentRegistry, DeterministicAgent
from core.models import Plan, SubTask
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


def build_nodes():
    return [
        DeviceNode(
            "device-1",
            {"private_file", "inference", "compute"},
            estimated_latency_ms=35,
            estimated_cost=0.0,
        ),
        EdgeNode(
            "edge-1",
            {"inference", "compute"},
            estimated_latency_ms=12,
            estimated_cost=0.2,
        ),
        CloudNode(
            "cloud-1",
            {"inference", "compute", "gpu"},
            estimated_latency_ms=45,
            estimated_cost=0.8,
        ),
    ]


def run_case(title, requirements, action):
    result = RuntimeExecutor().execute(requirements, build_nodes(), action)
    print(f"\n[{title}] success={result.success} target={result.deployment_target}")
    print(json.dumps(result.tool_records, ensure_ascii=False, indent=2))
    if not result.success:
        raise RuntimeError(f"demo case failed: {title}: {result.error}")
    return result


def main():
    private_result = run_case(
        "sensitive data stays on device",
        TaskRequirements(
            task_id="private-file",
            privacy_level="sensitive",
            required_capabilities={"private_file"},
        ),
        lambda node: f"processed private data on {node.node_id}",
    )
    assert private_result.deployment_target == "device"

    latency_result = run_case(
        "low latency prefers edge",
        TaskRequirements(
            task_id="low-latency-inference",
            required_capabilities={"inference"},
            max_latency_ms=20,
            preferred_tier="edge",
        ),
        lambda node: f"inference completed on {node.node_id}",
    )
    assert latency_result.deployment_target == "edge"

    def cloud_outage(node):
        if node.node_type == "cloud":
            raise NodeExecutionError("injected cloud outage")
        return f"compute completed on fallback {node.node_id}"

    fallback_result = run_case(
        "cloud outage falls back",
        TaskRequirements(
            task_id="high-compute",
            required_capabilities={"compute"},
            preferred_tier="cloud",
        ),
        cloud_outage,
    )
    assert [record["node_type"] for record in fallback_result.tool_records] == ["cloud", "edge"]

    registry = AgentRegistry()
    registry.register(NodeRoutedAgent(DeterministicAgent("worker"), build_nodes()))
    harness_report = Orchestrator(registry).run(
        Plan(
            "route a Harness task",
            [
                SubTask(
                    "harness-private-task",
                    "worker",
                    "process a private input through the existing Orchestrator",
                    max_retries=0,
                    metadata={
                        "privacy_level": "sensitive",
                        "required_capabilities": ["private_file"],
                    },
                )
            ],
        )
    )
    harness_result = harness_report.results["harness-private-task"]
    print(
        f"\n[harness integration] status={harness_report.status} "
        f"target={harness_result.tool_records[0]['node_type']}"
    )
    assert harness_report.status == "success"
    assert harness_result.tool_records[0]["node_type"] == "device"
    print("\nAll edge-cloud demo cases passed.")


if __name__ == "__main__":
    main()
