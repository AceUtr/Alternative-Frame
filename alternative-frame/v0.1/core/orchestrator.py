from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Dict, List, Mapping, Any, cast
import time

from .agents import Agent, AgentRegistry
from .acceptance import AcceptanceEvaluator
from .models import AgentResult, Plan, SubTask, utc_now
from .retry import RetryFailureClassifier


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
    executed_task_count: int = 0
    local_recovery_cycles: int = 0


class Orchestrator:
    """
    Centralized Main Agent coordinator with dependency-aware parallelism.

    Supports:
    - DAG execution
    - retry mechanism
    - acceptance evaluation
    - runtime tool injection
    """

    def __init__(
        self,
        registry: AgentRegistry,
        max_workers: int = 4,
        on_event: Callable | None = None,
        acceptance: AcceptanceEvaluator | None = None,
        retry_classifier: RetryFailureClassifier | None = None,
        tools: Any | None = None,
    ) -> None:

        self.registry = registry
        self.max_workers = max_workers
        self.on_event = on_event
        self.acceptance = acceptance
        self.retry_classifier = (
            retry_classifier or RetryFailureClassifier()
        )

        # 新增：统一工具系统入口
        self.tools = tools

        self._lock = Lock()


    def _emit(
        self,
        event: str,
        task: SubTask,
        result=None
    ) -> None:

        if self.on_event:
            self.on_event(
                event,
                task,
                result
            )


    def run(
        self,
        plan: Plan,
        parallel: bool = True
    ) -> RunReport:

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
                if all(
                    dep in results
                    and results[dep].status == "success"
                    for dep in task_map[task_id].depends_on
                )
            ]


            blocked = [
                task_map[task_id]
                for task_id in pending
                if any(
                    dep in results
                    and results[dep].status != "success"
                    for dep in task_map[task_id].depends_on
                )
            ]


            if not ready:

                for task in (
                    blocked
                    or [
                        task_map[task_id]
                        for task_id in pending
                    ]
                ):

                    failures.append(
                        f"{task.id}: blocked by failed dependency"
                    )

                break



            if parallel and len(ready) > 1:

                with ThreadPoolExecutor(
                    max_workers=min(
                        self.max_workers,
                        len(ready)
                    )
                ) as pool:

                    futures = {
                        pool.submit(
                            self._run_with_retry,
                            task,
                            results
                        ): task
                        for task in ready
                    }

                    batch = [
                        future.result()
                        for future in as_completed(futures)
                    ]

            else:

                batch = [
                    self._run_with_retry(
                        task,
                        results
                    )
                    for task in ready
                ]



            for task, result in batch:

                results[task.id] = result

                pending.remove(task.id)


                if result.status != "success":

                    failures.append(
                        f"{task.id}: "
                        f"{', '.join(result.failures) or result.status}"
                    )


        status = (
            "success"
            if (
                len(results) == len(task_map)
                and all(
                    r.status == "success"
                    for r in results.values()
                )
            )
            else
            "failed"
        )


        return RunReport(
            plan.goal,
            status,
            results,
            rounds,
            started,
            utc_now(),
            failures,
            started_epoch=started_epoch,
            finished_epoch=time.perf_counter()
        )



    def _run_with_retry(
        self,
        task: SubTask,
        current: Mapping[str, AgentResult]
    ) -> tuple[SubTask, AgentResult]:
        agent = cast(Agent, self.registry.get(task.role))
        accumulated_artifacts = []
        accumulated_evidence = []
        accumulated_tool_records = []
        retry_feedback = None
        max_attempts = max(1, task.max_retries + 1)

        for attempt in range(1, max_attempts + 1):
            attempt_task = deepcopy(task)
            attempt_task.metadata["runtime_attempt"] = attempt

            if retry_feedback:
                attempt_task.metadata["retry_feedback"] = retry_feedback.to_dict()

            self._emit("task_started", attempt_task)
            try:
                runtime_context: dict[str, Any] = dict(current)
                runtime_context["tools"] = self.tools
                last = agent.run(attempt_task, runtime_context)
            except Exception as exc:
                last = AgentResult(
                    task.id,
                    "failed",
                    summary="Agent execution raised an exception",
                    failures=[f"agent_exception: {type(exc).__name__}: {exc}"],
                )

            last.attempts = attempt
            accumulated_artifacts.extend(last.artifacts)
            accumulated_evidence.extend(last.evidence)
            accumulated_tool_records.extend(last.tool_records)
            last.artifacts = list(dict.fromkeys(accumulated_artifacts))
            deduplicated_evidence = []
            seen = set()
            for item in accumulated_evidence:
                key = str(item)
                if key not in seen:
                    seen.add(key)
                    deduplicated_evidence.append(item)

            last.evidence = deduplicated_evidence
            last.tool_records = list(accumulated_tool_records)

            if self.acceptance:
                acceptance = self.acceptance.evaluate(attempt_task, last)
                last.evidence.extend(acceptance.checks)
                if not acceptance.passed:
                    last.status = "failed"
                    last.failures.extend(acceptance.failures)

            self._emit("task_finished", attempt_task, last)

            if last.status == "success":
                return task, last

            if attempt >= max_attempts or not self.retry_classifier.retryable(last):
                return task, last

            retry_feedback = self.retry_classifier.build_feedback(task, last, attempt + 1)
            self._emit("task_retry_scheduled", attempt_task, last)

        return task, AgentResult(
            task.id,
            "failed",
            summary="Retry loop exited without producing a result",
            failures=["retry_loop_exhausted_without_result"],
        )
