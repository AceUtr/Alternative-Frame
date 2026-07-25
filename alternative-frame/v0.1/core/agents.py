from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, Mapping

from .models import AgentResult, SubTask, utc_now


class Agent(ABC):
    """Minimal role-based agent contract used by the orchestrator."""

    role: str

    @abstractmethod
    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        raise NotImplementedError


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if not getattr(agent, "role", None):
            raise ValueError("Agent must define a role")
        self._agents[agent.role] = agent

    def get(self, role: str) -> Agent:
        try:
            return self._agents[role]
        except KeyError as exc:
            raise KeyError(f"No agent registered for role: {role}") from exc

    def roles(self):
        return tuple(sorted(self._agents))

    def has(self, role: str) -> bool:
        return role in self._agents


@dataclass
class DeterministicAgent(Agent):
    """Local stub for validating orchestration before connecting an LLM."""

    role: str
    handler: Callable[[SubTask, Mapping[str, AgentResult]], str] | None = None

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        started = utc_now()
        try:
            summary = self.handler(task, context) if self.handler else f"{self.role} completed: {task.description}"
            return AgentResult(
                subtask_id=task.id,
                status="success",
                summary=summary,
                artifacts=[f"artifact://{task.id}"],
                evidence=[f"role={self.role}", f"acceptance_checks={len(task.acceptance)}"],
                started_at=started,
                finished_at=utc_now(),
            )
        except Exception as exc:  # Agent failures become structured results.
            return AgentResult(
                subtask_id=task.id,
                status="failed",
                summary=f"{self.role} failed",
                failures=[str(exc)],
                started_at=started,
                finished_at=utc_now(),
            )
