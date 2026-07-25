from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from .agents import Agent, AgentRegistry
from .long_horizon.acceptance_contract import AcceptanceContract
from .models import Plan
from .tools.registry import ToolRegistry


class DomainAdapter(ABC):
    """Stable boundary between a domain implementation and the core Harness."""

    name: str

    @abstractmethod
    def register_tools(self, registry: ToolRegistry, workspace: Path) -> None:
        """Register domain tools without replacing existing core tools."""
        raise NotImplementedError

    @abstractmethod
    def build_agents(self, model_client, tools: ToolRegistry) -> Iterable[Agent]:
        """Build role agents that use the supplied model client and tool registry."""
        raise NotImplementedError

    @abstractmethod
    def build_plan(self, goal: str) -> Plan:
        raise NotImplementedError

    @abstractmethod
    def build_contract(self, goal: str) -> AcceptanceContract:
        raise NotImplementedError

    def reset_workspace(self, workspace: Path) -> None:
        """Reset a reproducible fixture. Production adapters may leave this empty."""

    def configure(
        self,
        workspace: str | Path,
        model_client=None,
        tools: ToolRegistry | None = None,
        agents: AgentRegistry | None = None,
    ) -> tuple[ToolRegistry, AgentRegistry]:
        workspace_path = Path(workspace).resolve()
        tool_registry = tools or ToolRegistry()
        agent_registry = agents or AgentRegistry()
        self.register_tools(tool_registry, workspace_path)
        for agent in self.build_agents(model_client, tool_registry):
            agent_registry.register(agent)
        return tool_registry, agent_registry


class DomainRegistry:
    def __init__(self, adapters: Iterable[DomainAdapter] = ()) -> None:
        self._adapters: dict[str, DomainAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: DomainAdapter) -> None:
        name = str(getattr(adapter, "name", "")).strip()
        if not name:
            raise ValueError("DomainAdapter must define a non-empty name")
        if name in self._adapters:
            raise ValueError(f"domain already registered: {name}")
        self._adapters[name] = adapter

    def get(self, name: str) -> DomainAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise KeyError(f"domain is not registered: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def has(self, name: str) -> bool:
        return name in self._adapters
