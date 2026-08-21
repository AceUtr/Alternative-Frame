"""Deterministic Top-k context routing for centralized multi-Agent communication."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Mapping, Sequence, Tuple

from .models import AgentResult, SubTask


def _tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_./-]+|[\u4e00-\u9fff]{2,}", value or "")
        if len(token) > 1
    }


@dataclass(frozen=True)
class CommunicationCandidate:
    task_id: str
    role: str
    score: float
    reasons: Tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "role": self.role,
            "score": self.score,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class CommunicationDecision:
    receiver_task_id: str
    receiver_role: str
    top_k: int
    dependency_senders: Tuple[str, ...]
    selected_peer_senders: Tuple[str, ...]
    ranked_candidates: Tuple[CommunicationCandidate, ...] = field(default_factory=tuple)

    @property
    def delivered_senders(self) -> Tuple[str, ...]:
        return self.dependency_senders + self.selected_peer_senders

    def to_dict(self) -> dict:
        return {
            "receiver_task_id": self.receiver_task_id,
            "receiver_role": self.receiver_role,
            "top_k": self.top_k,
            "dependency_senders": list(self.dependency_senders),
            "selected_peer_senders": list(self.selected_peer_senders),
            "delivered_senders": list(self.delivered_senders),
            "ranked_candidates": [item.to_dict() for item in self.ranked_candidates],
        }


class TopKCommunicationRouter:
    """Keep required DAG context and select only the most relevant peer messages."""

    def __init__(self, default_top_k: int = 2, max_top_k: int = 8) -> None:
        if default_top_k < 0:
            raise ValueError("default_top_k cannot be negative")
        if max_top_k < 1 or default_top_k > max_top_k:
            raise ValueError("invalid Top-k bounds")
        self.default_top_k = default_top_k
        self.max_top_k = max_top_k

    def route(
        self,
        receiver: SubTask,
        completed: Mapping[str, AgentResult],
        task_map: Mapping[str, SubTask],
    ) -> tuple[Dict[str, AgentResult], CommunicationDecision]:
        configured = receiver.metadata.get("communication_top_k", self.default_top_k)
        try:
            top_k = int(configured)
        except (TypeError, ValueError) as exc:
            raise ValueError("communication_top_k must be an integer") from exc
        if top_k < 0 or top_k > self.max_top_k:
            raise ValueError(f"communication_top_k must be between 0 and {self.max_top_k}")

        dependencies = tuple(task_id for task_id in receiver.depends_on if task_id in completed)
        optional_ids = sorted(set(completed) - set(dependencies))
        ranked = sorted(
            (
                self._score(receiver, task_map[task_id], completed[task_id])
                for task_id in optional_ids
                if task_id in task_map
            ),
            key=lambda item: (-item.score, item.task_id),
        )
        selected = tuple(item.task_id for item in ranked[:top_k])
        delivered = dependencies + selected
        context = {task_id: completed[task_id] for task_id in delivered}
        decision = CommunicationDecision(
            receiver_task_id=receiver.id,
            receiver_role=receiver.role,
            top_k=top_k,
            dependency_senders=dependencies,
            selected_peer_senders=selected,
            ranked_candidates=tuple(ranked),
        )
        return context, decision

    @staticmethod
    def _score(
        receiver: SubTask,
        sender: SubTask,
        result: AgentResult,
    ) -> CommunicationCandidate:
        score = 0.0
        reasons = []
        preferred_roles = {
            str(role).strip() for role in receiver.metadata.get("communication_roles", [])
        }
        if sender.role in preferred_roles:
            score += 40.0
            reasons.append(f"preferred role={sender.role}")

        receiver_inputs = {str(item).replace("\\", "/") for item in receiver.inputs}
        sender_artifacts = {str(item).replace("\\", "/") for item in result.artifacts}
        matched_artifacts = sorted(receiver_inputs & sender_artifacts)
        if matched_artifacts:
            score += 60.0 + 5.0 * len(matched_artifacts)
            reasons.append("matched input artifacts=" + ",".join(matched_artifacts))

        receiver_topics = _tokens(
            " ".join(
                [receiver.description]
                + [str(item) for item in receiver.metadata.get("communication_topics", [])]
            )
        )
        sender_topics = _tokens(
            " ".join([sender.description, result.summary, *result.artifacts, *result.evidence])
        )
        overlap = sorted(receiver_topics & sender_topics)
        if overlap:
            score += min(30.0, 5.0 * len(overlap))
            reasons.append("topic overlap=" + ",".join(overlap[:6]))

        if result.status == "success":
            score += 5.0
            reasons.append("successful sender result")
        return CommunicationCandidate(
            task_id=sender.id,
            role=sender.role,
            score=round(score, 6),
            reasons=tuple(reasons or ["deterministic tie-break only"]),
        )


__all__ = [
    "CommunicationCandidate",
    "CommunicationDecision",
    "TopKCommunicationRouter",
]

