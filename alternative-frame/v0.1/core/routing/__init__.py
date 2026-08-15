from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Iterable, Mapping, Optional, Tuple

if TYPE_CHECKING:
    from core.runtime_nodes import ExecutionNode


PRIVACY_LEVELS = {"public", "internal", "sensitive"}
NODE_TYPES = {"device", "edge", "cloud"}


class NoEligibleNodeError(RuntimeError):
    """Raised when no node satisfies all hard task constraints."""


@dataclass
class TaskRequirements:
    task_id: str = ""
    privacy_level: str = "public"
    required_capabilities: frozenset[str] = field(default_factory=frozenset)
    max_latency_ms: Optional[float] = None
    max_cost: Optional[float] = None
    network_required: bool = False
    preferred_tier: Optional[str] = None
    allow_fallback: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.task_id = str(self.task_id).strip()
        self.privacy_level = str(self.privacy_level).strip().lower()
        self.required_capabilities = frozenset(
            str(item).strip() for item in self.required_capabilities if str(item).strip()
        )
        if self.privacy_level not in PRIVACY_LEVELS:
            raise ValueError(f"unsupported privacy_level: {self.privacy_level}")
        if self.preferred_tier is not None:
            self.preferred_tier = str(self.preferred_tier).strip().lower()
            if self.preferred_tier not in NODE_TYPES:
                raise ValueError(f"unsupported preferred_tier: {self.preferred_tier}")
        if self.max_latency_ms is not None and self.max_latency_ms < 0:
            raise ValueError("max_latency_ms cannot be negative")
        if self.max_cost is not None and self.max_cost < 0:
            raise ValueError("max_cost cannot be negative")

    @classmethod
    def from_metadata(cls, task_id: str, metadata: Mapping[str, Any]) -> "TaskRequirements":
        """Build requirements from the frozen ``SubTask.metadata`` extension point."""
        return cls(
            task_id=task_id,
            privacy_level=metadata.get("privacy_level", "public"),
            required_capabilities=frozenset(metadata.get("required_capabilities", [])),
            max_latency_ms=metadata.get("max_latency_ms"),
            max_cost=metadata.get("max_cost"),
            network_required=bool(metadata.get("network_required", False)),
            preferred_tier=metadata.get("preferred_tier") or metadata.get("deployment_target"),
            allow_fallback=bool(metadata.get("allow_fallback", True)),
            metadata=dict(metadata),
        )


@dataclass(frozen=True)
class PlacementDecision:
    selected_node: Optional["ExecutionNode"]
    score: Optional[float]
    reasons: Tuple[str, ...]
    rejected_nodes: Mapping[str, Tuple[str, ...]]
    ranked_node_ids: Tuple[str, ...] = ()
    candidate_scores: Mapping[str, float] = field(default_factory=dict)
    candidate_reasons: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)

    @property
    def selected_node_id(self) -> Optional[str]:
        return self.selected_node.node_id if self.selected_node else None

    @property
    def selected_node_type(self) -> Optional[str]:
        return self.selected_node.node_type if self.selected_node else None

    def require_node(self) -> ExecutionNode:
        if self.selected_node is None:
            detail = "; ".join(
                f"{node_id}: {', '.join(reasons)}"
                for node_id, reasons in self.rejected_nodes.items()
            )
            raise NoEligibleNodeError(detail or "no execution nodes were provided")
        return self.selected_node

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.selected_node_id,
            "node_type": self.selected_node_type,
            "score": self.score,
            "placement_reason": "; ".join(self.reasons),
            "rejected_nodes": {key: list(value) for key, value in self.rejected_nodes.items()},
            "ranked_node_ids": list(self.ranked_node_ids),
            "candidate_scores": dict(self.candidate_scores),
            "candidate_reasons": {
                key: list(value) for key, value in self.candidate_reasons.items()
            },
        }


class NodeRouter:
    """Deterministic hard-filter-then-score placement router."""

    def route(
        self,
        requirements: TaskRequirements,
        nodes: Iterable["ExecutionNode"],
    ) -> PlacementDecision:
        eligible = []
        rejected: Dict[str, Tuple[str, ...]] = {}

        for node in sorted(nodes, key=lambda item: item.node_id):
            failures = self._hard_constraint_failures(requirements, node)
            if failures:
                rejected[node.node_id] = tuple(failures)
                continue
            score, reasons = self._score(requirements, node)
            eligible.append((score, node, tuple(reasons)))

        if not eligible:
            return PlacementDecision(
                selected_node=None,
                score=None,
                reasons=("no node satisfies all hard constraints",),
                rejected_nodes=rejected,
            )

        eligible.sort(
            key=lambda item: (
                -item[0],
                item[1].estimated_latency_ms,
                item[1].estimated_cost,
                item[1].node_id,
            )
        )
        score, selected, reasons = eligible[0]
        return PlacementDecision(
            selected_node=selected,
            score=round(score, 6),
            reasons=reasons,
            rejected_nodes=rejected,
            ranked_node_ids=tuple(item[1].node_id for item in eligible),
            candidate_scores={item[1].node_id: round(item[0], 6) for item in eligible},
            candidate_reasons={item[1].node_id: item[2] for item in eligible},
        )

    @staticmethod
    def _hard_constraint_failures(
        requirements: TaskRequirements,
        node: "ExecutionNode",
    ) -> list[str]:
        failures = []
        if not node.online:
            failures.append("node is offline")
        if requirements.network_required and not node.network_available:
            failures.append("required network is unavailable")
        if requirements.privacy_level == "sensitive" and node.node_type != "device":
            failures.append("sensitive data must remain on device")
        missing = sorted(requirements.required_capabilities - node.capabilities)
        if missing:
            failures.append(f"missing capabilities: {', '.join(missing)}")
        if (
            requirements.max_latency_ms is not None
            and node.estimated_latency_ms > requirements.max_latency_ms
        ):
            failures.append(
                f"estimated latency {node.estimated_latency_ms:g}ms exceeds "
                f"limit {requirements.max_latency_ms:g}ms"
            )
        if requirements.max_cost is not None and node.estimated_cost > requirements.max_cost:
            failures.append(
                f"estimated cost {node.estimated_cost:g} exceeds limit {requirements.max_cost:g}"
            )
        return failures

    @staticmethod
    def _score(requirements: TaskRequirements, node: "ExecutionNode") -> tuple[float, list[str]]:
        score = 100.0
        reasons = ["all hard constraints satisfied"]

        if requirements.preferred_tier == node.node_type:
            score += 30.0
            reasons.append(f"matches preferred tier {node.node_type}")
        if requirements.privacy_level == "sensitive" and node.node_type == "device":
            score += 40.0
            reasons.append("keeps sensitive data on device")

        # Prefer lower latency and cost without allowing either soft preference
        # to override a failed hard constraint.
        score += 25.0 / (1.0 + node.estimated_latency_ms / 100.0)
        score += 20.0 / (1.0 + node.estimated_cost)
        reasons.append(
            f"estimated latency={node.estimated_latency_ms:g}ms cost={node.estimated_cost:g}"
        )
        return score, reasons


__all__ = [
    "NoEligibleNodeError",
    "NodeRouter",
    "PlacementDecision",
    "TaskRequirements",
]
