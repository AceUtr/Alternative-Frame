from __future__ import annotations

import json
from typing import Mapping

from .agents import Agent
from .model_client import OpenAICompatibleClient
from .models import AgentResult, SubTask, utc_now


class ConfiguredModelAgent(Agent):
    """A role-specific prompt running on the user-selected shared model."""

    def __init__(self, role: str, client: OpenAICompatibleClient, system_prompt: str):
        self.role = role
        self.client = client
        self.system_prompt = system_prompt

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        started = utc_now()
        dependency_summary = [
            {"task_id": key, "status": value.status, "summary": value.summary, "artifacts": value.artifacts}
            for key, value in context.items()
        ]
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": json.dumps({
                "task_id": task.id,
                "role": self.role,
                "description": task.description,
                "acceptance": task.acceptance,
                "dependencies": dependency_summary,
            }, ensure_ascii=False)},
        ]
        try:
            message = self.client.chat(messages)
            content = message.get("content", "") if isinstance(message, dict) else str(message)
            return AgentResult(
                subtask_id=task.id,
                status="success",
                summary=content,
                evidence=[f"model={self.client.config.model}", "api_response_received"],
                artifacts=[],
                started_at=started,
                finished_at=utc_now(),
            )
        except Exception as exc:
            return AgentResult(
                subtask_id=task.id,
                status="failed",
                summary=f"{self.role} API call failed",
                failures=[str(exc)],
                evidence=[f"model={self.client.config.model}"],
                started_at=started,
                finished_at=utc_now(),
            )

