from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SubTask:
    id: str
    role: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    acceptance: List[str] = field(default_factory=list)
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    subtask_id: str
    status: str  # success / failed / timeout
    summary: str = ""
    artifacts: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    tool_records: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    attempts: int = 1
    started_at: str = field(default_factory=utc_now)
    finished_at: str = field(default_factory=utc_now)


@dataclass
class Plan:
    goal: str
    subtasks: List[SubTask]
    final_acceptance: List[str] = field(default_factory=list)

    def task_map(self) -> Dict[str, SubTask]:
        return {task.id: task for task in self.subtasks}

    def validate(self) -> None:
        tasks = self.task_map()
        if len(tasks) != len(self.subtasks):
            raise ValueError("SubTask ids must be unique")
        for task in self.subtasks:
            missing = set(task.depends_on) - set(tasks)
            if missing:
                raise ValueError(f"{task.id} depends on missing tasks: {sorted(missing)}")
        # Detect cycles with a small DFS; fail before execution starts.
        visiting, visited = set(), set()
        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError(f"Cycle detected at task: {task_id}")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dep in tasks[task_id].depends_on:
                visit(dep)
            visiting.remove(task_id)
            visited.add(task_id)
        for task_id in tasks:
            visit(task_id)
