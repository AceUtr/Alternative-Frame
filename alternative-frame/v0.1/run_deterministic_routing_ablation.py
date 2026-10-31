from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from core.routing import TaskRequirements
from core.runtime_nodes import (
    CloudNode,
    DeviceNode,
    EdgeNode,
    NodeExecutionError,
    RuntimeExecutor,
)


def build_nodes():
    return [
        DeviceNode(
            "device-1",
            {"compute"},
            estimated_latency_ms=35,
            estimated_cost=0.0,
        ),
        EdgeNode(
            "edge-1",
            {"compute"},
            estimated_latency_ms=12,
            estimated_cost=0.2,
        ),
        CloudNode(
            "cloud-1",
            {"compute"},
            estimated_latency_ms=45,
            estimated_cost=0.8,
        ),
    ]


def injected_cloud_outage(node):
    if node.node_type == "cloud":
        raise NodeExecutionError("injected cloud outage")
    return f"completed on {node.node_id}"


@dataclass
class RoutingResult:
    mode: str
    completed: bool
    selected_node: str | None
    final_node_type: str | None
    fallback_count: int
    execution_attempts: int
    failed_attempts: int

    device_attempts: int
    edge_attempts: int
    cloud_attempts: int

    estimated_latency_ms: float | None
    estimated_cost: float | None
    actual_duration_seconds: float

    tool_records: List[Dict[str, Any]]
    evidence_kind: str = "deterministic_controlled_run"


def run_fixed_cloud() -> RoutingResult:
    cloud = CloudNode(
        "cloud-1",
        {"compute"},
        estimated_latency_ms=45,
        estimated_cost=0.8,
    )

    started = datetime.now(timezone.utc)

    try:
        injected_cloud_outage(cloud)
        completed = True
        records = [
            {
                "node": "cloud",
                "node_type": "cloud",
                "node_id": "cloud-1",
                "success": True,
                "estimated_latency_ms": 45,
                "estimated_cost": 0.8,
                "fallback_count": 0,
            }
        ]
    except Exception as exc:
        completed = False
        records = [
            {
                "node": "cloud",
                "node_type": "cloud",
                "node_id": "cloud-1",
                "success": False,
                "estimated_latency_ms": 45,
                "estimated_cost": 0.8,
                "fallback_count": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        ]

    finished = datetime.now(timezone.utc)

    return RoutingResult(
        mode="fixed_cloud",
        completed=completed,
        selected_node="cloud-1",
        final_node_type="cloud",
        fallback_count=0,
        execution_attempts=1,
        failed_attempts=0 if completed else 1,
        device_attempts=0,
        edge_attempts=0,
        cloud_attempts=1,
        estimated_latency_ms=45,
        estimated_cost=0.8,
        actual_duration_seconds=max(
            (finished - started).total_seconds(),
            0.0,
        ),
        tool_records=records,
    )


def run_dynamic() -> RoutingResult:
    result = RuntimeExecutor().execute(
        TaskRequirements(
            task_id="high-compute",
            required_capabilities={"compute"},
            preferred_tier="cloud",
            allow_fallback=True,
        ),
        build_nodes(),
        injected_cloud_outage,
    )

    records = list(result.tool_records)

    return RoutingResult(
        mode="dynamic_routing",
        completed=bool(result.success),
        selected_node=result.selected_node_id,
        final_node_type=(
            result.selected_node.node_type
            if result.selected_node
            else None
        ),
        fallback_count=int(result.fallback_count),
        execution_attempts=len(records),
        failed_attempts=sum(
            record.get("success") is not True
            for record in records
        ),
        device_attempts=sum(
            record.get("node_type") == "device"
            for record in records
        ),
        edge_attempts=sum(
            record.get("node_type") == "edge"
            for record in records
        ),
        cloud_attempts=sum(
            record.get("node_type") == "cloud"
            for record in records
        ),
        estimated_latency_ms=(
            records[-1].get("estimated_latency_ms")
            if records
            else None
        ),
        estimated_cost=(
            records[-1].get("estimated_cost")
            if records
            else None
        ),
        actual_duration_seconds=sum(
            float(record.get("duration_seconds") or 0.0)
            for record in records
        ),
        tool_records=records,
    )


def run_mode(mode: str) -> RoutingResult:
    if mode == "fixed_cloud":
        return run_fixed_cloud()

    if mode == "dynamic_routing":
        return run_dynamic()

    raise ValueError(
        "mode must be fixed_cloud or dynamic_routing"
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        default="benchmarks/configs/deterministic_routing.json",
    )

    args = parser.parse_args()

    config = json.loads(
        Path(args.config).read_text(
            encoding="utf-8-sig"
        )
    )

    results = []

    for mode in config.get(
        "modes",
        ["fixed_cloud", "dynamic_routing"],
    ):
        result = run_mode(mode)
        results.append(asdict(result))

        print(
            f"{mode}: "
            f"completed={result.completed} "
            f"final_node={result.final_node_type} "
            f"fallback={result.fallback_count} "
            f"attempts={result.execution_attempts} "
            f"cloud={result.cloud_attempts} "
            f"edge={result.edge_attempts}"
        )

    output_dir = Path(
        "benchmarks/results/summary"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S%fZ")

    output_path = (
        output_dir
        / f"deterministic_routing-{timestamp}.json"
    )

    output_path.write_text(
        json.dumps(
            {
                "experiment": config.get(
                    "name",
                    "deterministic_routing_ablation",
                ),
                "evidence_kind": (
                    "deterministic_controlled_run"
                ),
                "generated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"results={output_path.resolve()}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
