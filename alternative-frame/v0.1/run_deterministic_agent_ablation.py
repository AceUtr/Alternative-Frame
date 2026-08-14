"""Deterministic single-agent vs multi-agent orchestration ablation.

No model API is required.

The task logic, DAG, and success conditions are identical.

single_agent:
    all logical roles delegate to one shared backend;
    the backend serializes work with one lock.

multi_agent:
    each logical role has its own backend;
    independent DAG nodes can execute concurrently through the real
    Orchestrator thread pool.

This experiment measures orchestration parallelism and role topology.
It does NOT claim that deterministic multi-agent reasoning is smarter.
"""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from core.agents import Agent, AgentRegistry
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator


ROLES = (
    "analyst",
    "architect",
    "developer",
    "tester",
    "reviewer",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeterministicBackend:
    """Identical deterministic task implementation for every condition."""

    def __init__(
        self,
        backend_id: str,
        delay_seconds: float,
        serialize: bool,
    ):
        self.backend_id = backend_id
        self.delay_seconds = delay_seconds
        self.serialize = serialize

        self.lock = threading.Lock()
        self.calls: List[Dict] = []

    def run(self, task, context):
        if self.serialize:
            with self.lock:
                return self._execute(task, context)

        return self._execute(task, context)

    def _execute(self, task, context):
        started = time.perf_counter()

        time.sleep(self.delay_seconds)

        finished = time.perf_counter()

        self.calls.append(
            {
                "task_id": task.id,
                "role": task.role,
                "backend_id": self.backend_id,
                "started": started,
                "finished": finished,
            }
        )

        return AgentResult(
            task.id,
            "success",
            summary=(
                f"{task.id} completed by "
                f"{self.backend_id}"
            ),
            evidence=[
                "deterministic_agent_ablation"
            ],
            attempts=1,
        )


class RoleAgent(Agent):
    """Expose one logical role while delegating to a backend."""

    def __init__(
        self,
        role: str,
        backend: DeterministicBackend,
    ):
        self.role = role
        self.backend = backend

    def run(self, task, context):
        return self.backend.run(task, context)


def build_plan() -> Plan:
    """A DAG with meaningful parallel work.

                  analyze
                 /      \
          architecture  implementation
                 \      /
                   test
                    |
                  review

    architecture and implementation are both ready after analyze.
    """

    return Plan(
        "Complete deterministic software workflow.",
        [
            SubTask(
                "analyze",
                "analyst",
                "Analyze requirements.",
            ),
            SubTask(
                "architecture",
                "architect",
                "Design architecture.",
                depends_on=["analyze"],
            ),
            SubTask(
                "implementation",
                "developer",
                "Implement solution.",
                depends_on=["analyze"],
            ),
            SubTask(
                "test",
                "tester",
                "Verify architecture and implementation.",
                depends_on=[
                    "architecture",
                    "implementation",
                ],
            ),
            SubTask(
                "review",
                "reviewer",
                "Perform final review.",
                depends_on=["test"],
            ),
        ],
    )


def build_single_registry(
    delay_seconds: float,
):
    registry = AgentRegistry()

    shared = DeterministicBackend(
        backend_id="universal_agent",
        delay_seconds=delay_seconds,
        serialize=True,
    )

    for role in ROLES:
        registry.register(
            RoleAgent(role, shared)
        )

    return registry, [shared]


def build_multi_registry(
    delay_seconds: float,
):
    registry = AgentRegistry()
    backends = []

    for role in ROLES:
        backend = DeterministicBackend(
            backend_id=f"{role}_agent",
            delay_seconds=delay_seconds,
            serialize=False,
        )

        backends.append(backend)

        registry.register(
            RoleAgent(role, backend)
        )

    return registry, backends


def overlap_seconds(
    calls: List[Dict],
) -> float:
    """Measure overlap between architecture and implementation."""

    lookup = {
        item["task_id"]: item
        for item in calls
    }

    left = lookup.get("architecture")
    right = lookup.get("implementation")

    if not left or not right:
        return 0.0

    start = max(
        left["started"],
        right["started"],
    )

    end = min(
        left["finished"],
        right["finished"],
    )

    return max(end - start, 0.0)


@dataclass
class AgentRunResult:
    mode: str
    status: str
    goal_completed: bool

    task_count: int
    success_count: int
    first_pass_count: int

    logical_role_count: int
    unique_backend_count: int

    handoff_count: int
    rounds: int

    duration_seconds: float
    parallel_overlap_seconds: float

    execution_backends: Dict[str, str]

    evidence_kind: str = (
        "deterministic_controlled_run"
    )


def run_once(
    mode: str,
    delay_seconds: float,
) -> AgentRunResult:

    if mode == "single_agent":
        registry, backends = (
            build_single_registry(
                delay_seconds
            )
        )

    elif mode == "multi_agent":
        registry, backends = (
            build_multi_registry(
                delay_seconds
            )
        )

    else:
        raise ValueError(
            "mode must be single_agent "
            "or multi_agent"
        )

    plan = build_plan()

    orchestrator = Orchestrator(
        registry,
        max_workers=5,
    )

    started = time.perf_counter()

    # Both conditions use the SAME real Orchestrator
    # and the SAME parallel=True policy.
    report = orchestrator.run(
        plan,
        parallel=True,
    )

    elapsed = (
        time.perf_counter() - started
    )

    all_calls = [
        item
        for backend in backends
        for item in backend.calls
    ]

    execution_backends = {
        item["task_id"]: item["backend_id"]
        for item in all_calls
    }

    ordered_tasks = [
        "analyze",
        "architecture",
        "implementation",
        "test",
        "review",
    ]

    handoffs = 0

    previous_backend = None

    for task_id in ordered_tasks:
        backend = execution_backends.get(
            task_id
        )

        if (
            previous_backend is not None
            and backend is not None
            and backend != previous_backend
        ):
            handoffs += 1

        if backend is not None:
            previous_backend = backend

    return AgentRunResult(
        mode=mode,
        status=report.status,
        goal_completed=(
            report.status == "success"
        ),
        task_count=len(plan.subtasks),
        success_count=sum(
            result.status == "success"
            for result in report.results.values()
        ),
        first_pass_count=sum(
            result.status == "success"
            and result.attempts == 1
            for result in report.results.values()
        ),
        logical_role_count=len(ROLES),
        unique_backend_count=len(
            {
                item["backend_id"]
                for item in all_calls
            }
        ),
        handoff_count=handoffs,
        rounds=report.rounds,
        duration_seconds=elapsed,
        parallel_overlap_seconds=(
            overlap_seconds(all_calls)
        ),
        execution_backends=(
            execution_backends
        ),
    )


def summarize(
    mode: str,
    runs: List[AgentRunResult],
):
    durations = [
        run.duration_seconds
        for run in runs
    ]

    overlaps = [
        run.parallel_overlap_seconds
        for run in runs
    ]

    return {
        "mode": mode,
        "n": len(runs),
        "goal_completion_rate": (
            sum(
                run.goal_completed
                for run in runs
            )
            / len(runs)
        ),
        "mean_duration_seconds": (
            statistics.mean(durations)
        ),
        "median_duration_seconds": (
            statistics.median(durations)
        ),
        "min_duration_seconds": (
            min(durations)
        ),
        "max_duration_seconds": (
            max(durations)
        ),
        "mean_parallel_overlap_seconds": (
            statistics.mean(overlaps)
        ),
        "unique_backend_count": (
            runs[0].unique_backend_count
        ),
        "handoff_count": (
            runs[0].handoff_count
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--config",
        default=(
            "benchmarks/configs/"
            "deterministic_agents.json"
        ),
    )

    args = parser.parse_args()

    config = json.loads(
        Path(args.config).read_text(
            encoding="utf-8-sig"
        )
    )

    delay = float(
        config.get(
            "task_delay_seconds",
            0.08,
        )
    )

    repeats = int(
        config.get("repeats", 5)
    )

    modes = config.get(
        "modes",
        [
            "single_agent",
            "multi_agent",
        ],
    )

    raw_runs = []
    summaries = []

    for mode in modes:
        mode_runs = []

        for index in range(repeats):
            result = run_once(
                mode,
                delay,
            )

            mode_runs.append(result)
            raw_runs.append(
                {
                    "repeat_index": index,
                    **asdict(result),
                }
            )

        summary = summarize(
            mode,
            mode_runs,
        )

        summaries.append(summary)

        print(
            f"{mode}: "
            f"completion="
            f"{summary['goal_completion_rate']:.2f} "
            f"mean_duration="
            f"{summary['mean_duration_seconds']:.4f}s "
            f"backends="
            f"{summary['unique_backend_count']} "
            f"handoffs="
            f"{summary['handoff_count']} "
            f"overlap="
            f"{summary['mean_parallel_overlap_seconds']:.4f}s"
        )

    summary_map = {
        row["mode"]: row
        for row in summaries
    }

    if (
        "single_agent" in summary_map
        and "multi_agent" in summary_map
    ):
        single = summary_map[
            "single_agent"
        ][
            "mean_duration_seconds"
        ]

        multi = summary_map[
            "multi_agent"
        ][
            "mean_duration_seconds"
        ]

        speedup = (
            single / multi
            if multi > 0
            else None
        )

        print(
            f"wall_clock_speedup="
            f"{speedup:.3f}x"
            if speedup is not None
            else "wall_clock_speedup=unknown"
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
    ).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )

    output_path = (
        output_dir
        / (
            "deterministic_agents-"
            f"{timestamp}.json"
        )
    )

    payload = {
        "experiment": config.get(
            "name",
            "deterministic_agent_ablation",
        ),
        "evidence_kind": (
            "deterministic_controlled_run"
        ),
        "claim_scope": (
            "orchestration parallelism and "
            "role topology only"
        ),
        "repeats": repeats,
        "task_delay_seconds": delay,
        "runs": raw_runs,
        "summaries": summaries,
    }

    output_path.write_text(
        json.dumps(
            payload,
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
