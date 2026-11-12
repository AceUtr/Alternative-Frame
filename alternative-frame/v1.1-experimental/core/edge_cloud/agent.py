from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping

from ..agents import Agent
from ..models import AgentResult, SubTask, utc_now


@dataclass(frozen=True)
class RemoteNode:
    node_id: str
    role: str
    base_url: str

    @property
    def execute_url(self) -> str:
        return self.base_url.rstrip("/") + "/execute"

    @property
    def health_url(self) -> str:
        return self.base_url.rstrip("/") + "/health"


class RoutedRemoteAgent(Agent):
    """Execute allowlisted remote tasks in priority order and fall back on transport failure."""

    role = "remote_worker"

    def __init__(
        self,
        nodes: list[RemoteNode],
        token: str,
        run_id: str,
        timeout_seconds: float = 8,
        on_event: Callable[[str, dict], None] | None = None,
    ):
        if not nodes or timeout_seconds <= 0:
            raise ValueError("at least one node and a positive timeout are required")
        self.nodes = list(nodes)
        self.token = token
        self.run_id = run_id
        self.timeout_seconds = timeout_seconds
        self.on_event = on_event

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        started_at = utc_now()
        payload = task.metadata.get("remote_payload")
        if not isinstance(payload, dict):
            return AgentResult(task.id, "failed", failures=["remote_payload must be an object"])
        request_body = json.dumps({
            "run_id": self.run_id,
            "task_id": task.id,
            "description": task.description,
            "operation": "digest",
            "payload": payload,
            "dependencies": {task_id: result.summary[:1000] for task_id, result in context.items()},
        }, ensure_ascii=False).encode("utf-8")
        failures = []
        for index, node in enumerate(self.nodes):
            self._emit("remote_attempt_started", {
                "run_id": self.run_id, "task_id": task.id, "node_id": node.node_id,
                "node_role": node.role, "endpoint": node.base_url, "attempt": index + 1,
            })
            request = urllib.request.Request(
                node.execute_url,
                data=request_body,
                headers={"Content-Type": "application/json", "X-AF-Token": self.token},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    decoded = json.loads(response.read(65536))
                result = decoded.get("result") if decoded.get("success") is True else None
                if (
                    not isinstance(result, dict)
                    or result.get("task_id") != task.id
                    or result.get("run_id") != self.run_id
                    or result.get("node_id") != node.node_id
                    or result.get("node_role") != node.role
                    or not re.fullmatch(r"[0-9a-f]{64}", str(result.get("digest", "")))
                ):
                    raise ValueError("remote response failed run/task identity validation")
                expected_digest = task.metadata.get("expected_remote_digest")
                if expected_digest and result.get("digest") != expected_digest:
                    raise ValueError("remote response digest does not match the task input")
                self._emit("remote_task_completed", {
                    "run_id": self.run_id, "task_id": task.id, "node_id": node.node_id,
                    "node_role": node.role, "host": result.get("host"),
                    "host_fingerprint": result.get("host_fingerprint"),
                    "digest": result.get("digest"), "attempt": index + 1,
                })
                return AgentResult(
                    subtask_id=task.id,
                    status="success",
                    summary=json.dumps(result, ensure_ascii=False, sort_keys=True),
                    evidence=[
                        f"execution_node={node.node_id}",
                        f"execution_role={node.role}",
                        f"execution_host={result.get('host', 'unknown')}",
                        f"execution_host_fingerprint={result.get('host_fingerprint', 'unknown')}",
                        f"remote_attempts={index + 1}",
                    ],
                    tool_records=[{
                        "tool": "remote_node_executor",
                        "success": True,
                        "exit_code": 0,
                        "arguments": {"task_id": task.id, "node_id": node.node_id},
                        "metadata": {
                            "node_role": node.role,
                            "host": result.get("host"),
                            "host_fingerprint": result.get("host_fingerprint"),
                            "digest": result.get("digest"),
                        },
                    }],
                    attempts=index + 1,
                    started_at=started_at,
                    finished_at=utc_now(),
                )
            except (OSError, TimeoutError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
                detail = f"{type(exc).__name__}: {str(exc)[:300]}"
                failures.append(f"{node.node_id}: {detail}")
                self._emit("remote_attempt_failed", {
                    "run_id": self.run_id, "task_id": task.id, "node_id": node.node_id,
                    "node_role": node.role, "attempt": index + 1,
                    "error_type": type(exc).__name__, "error": str(exc)[:300],
                })
                if index + 1 < len(self.nodes):
                    self._emit("remote_failover", {
                        "run_id": self.run_id, "task_id": task.id,
                        "from_node": node.node_id, "to_node": self.nodes[index + 1].node_id,
                        "reason": type(exc).__name__,
                    })
        return AgentResult(
            subtask_id=task.id,
            status="failed",
            summary="all eligible remote nodes failed",
            failures=failures or ["no remote node attempts were made"],
            attempts=len(failures),
            started_at=started_at,
            finished_at=utc_now(),
        )

    def _emit(self, event: str, payload: dict) -> None:
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass
