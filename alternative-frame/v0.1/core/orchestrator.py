from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Dict, Iterable, List, Mapping
import time

from .agents import AgentRegistry
from .acceptance import AcceptanceEvaluator
from .models import AgentResult, Plan, SubTask, utc_now


@dataclass
class RunReport:
    goal: str
    status: str
    results: Dict[str, AgentResult]
    rounds: int
    started_at: str
    finished_at: str
    failures: List[str] = field(default_factory=list)
    started_epoch: float = 0.0
    finished_epoch: float = 0.0


class Orchestrator:
    """Centralized Main Agent coordinator with dependency-aware parallelism."""

    def __init__(self, registry: AgentRegistry, max_workers: int = 4, on_event: Callable | None = None, acceptance: AcceptanceEvaluator | None = None) -> None:
        self.registry = registry
        self.max_workers = max_workers
        self.on_event = on_event
        self.acceptance = acceptance
        self._lock = Lock()

    def _emit(self, event: str, task: SubTask, result=None) -> None:
        if self.on_event:
            self.on_event(event, task, result)

    def run(self, plan: Plan, parallel: bool = True) -> RunReport:
        plan.validate()
        started = utc_now()
        started_epoch = time.perf_counter()
        task_map = plan.task_map()
        results: Dict[str, AgentResult] = {}
        pending = set(task_map)
        failures: List[str] = []
        rounds = 0

        while pending:
            rounds += 1
            ready = [
                task_map[task_id]
                for task_id in sorted(pending)
                if all(dep in results and results[dep].status == "success" for dep in task_map[task_id].depends_on)
            ]
            blocked = [
                task_map[task_id]
                for task_id in pending
                if any(dep in results and results[dep].status != "success" for dep in task_map[task_id].depends_on)
            ]
            if not ready:
                for task in blocked or [task_map[task_id] for task_id in pending]:
                    failures.append(f"{task.id}: blocked by failed dependency")
                break

            if parallel and len(ready) > 1:
                with ThreadPoolExecutor(max_workers=min(self.max_workers, len(ready))) as pool:
                    futures = {pool.submit(self._run_with_retry, task, results): task for task in ready}
                    batch = [future.result() for future in as_completed(futures)]
            else:
                batch = [self._run_with_retry(task, results) for task in ready]

            for task, result in batch:
                results[task.id] = result
                pending.remove(task.id)
                if result.status != "success":
                    failures.append(f"{task.id}: {', '.join(result.failures) or result.status}")

        status = "success" if len(results) == len(task_map) and all(r.status == "success" for r in results.values()) else "failed"
        return RunReport(plan.goal, status, results, rounds, started, utc_now(), failures, started_epoch=started_epoch, finished_epoch=time.perf_counter())

    def _run_with_retry(self, task: SubTask, current: Mapping[str, AgentResult]):
        agent = self.registry.get(task.role)
        last = None
        for attempt in range(1, task.max_retries + 2):
            self._emit("task_started", task)
            last = agent.run(task, dict(current))
            last.attempts = attempt
            if self.acceptance:
                acceptance = self.acceptance.evaluate(task, last)
                last.evidence.extend(acceptance.checks)
                if not acceptance.passed:
                    last.status = "failed"
                    last.failures.extend(acceptance.failures)
            self._emit("task_finished", task, last)
            if last.status == "success":
                return task, last
            if any(code in last.failures for code in ("max_tool_steps_exceeded", "repeated_tool_call")):
                # Retrying the same unchanged plan would repeat the same costly
                # model/tool loop. Surface it to MainAgent for replanning.
                return task, last
        return task, last
