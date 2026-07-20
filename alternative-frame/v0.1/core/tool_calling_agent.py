from __future__ import annotations

import json
from typing import Mapping

from .agents import Agent
from .models import AgentResult, SubTask, utc_now
from .model_client import OpenAICompatibleClient
from .tools import ToolRegistry


class ToolCallingAgent(Agent):
    """LLM agent loop: model decides, registry executes, model observes."""

    def __init__(self, role: str, client: OpenAICompatibleClient, tools: ToolRegistry, system_prompt: str, max_steps: int = 20):
        self.role, self.client, self.tools, self.system_prompt, self.max_steps = role, client, tools, system_prompt, max_steps

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        started = utc_now()
        protocol = (
            "\n\nTOOL PROTOCOL:\n"
            "1. Use tools only when an actual workspace action is necessary.\n"
            "2. After the requested artifacts exist and relevant checks pass, STOP calling tools.\n"
            "3. Return a concise final response with: completed work, artifact paths, checks run, and remaining risks.\n"
            "4. Never repeat the same tool call with identical arguments unless the previous result failed and you changed the plan."
        )
        messages = [{"role": "system", "content": self.system_prompt + protocol}, {"role": "user", "content": json.dumps({"task": task.description, "acceptance": task.acceptance, "dependencies": {k: v.summary for k, v in context.items()},}, ensure_ascii=False)}]
        evidence, artifacts = [], []
        call_counts = {}
        for step in range(self.max_steps):
            response = self.client.chat(messages, tools=self.tools.schemas())
            tool_calls = response.get("tool_calls", []) if isinstance(response, dict) else []
            if not tool_calls:
                content = response.get("content", "") if isinstance(response, dict) else str(response)
                return AgentResult(task.id, "success", summary=content, artifacts=artifacts, evidence=evidence + [f"model_step={step + 1}"], started_at=started, finished_at=utc_now())
            messages.append({"role": "assistant", "content": response.get("content", ""), "tool_calls": tool_calls})
            for call in tool_calls:
                name = call.get("function", {}).get("name", "")
                raw_args = call.get("function", {}).get("arguments", {})
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                signature = name + ":" + json.dumps(args, ensure_ascii=False, sort_keys=True)
                call_counts[signature] = call_counts.get(signature, 0) + 1
                if call_counts[signature] >= 3:
                    return AgentResult(task.id, "failed", summary="repeated identical tool call detected", evidence=evidence, failures=["repeated_tool_call"], started_at=started, finished_at=utc_now())
                result = self.tools.execute(name, args)
                evidence.append(f"tool={name};success={result.success}")
                if result.success and result.metadata.get("artifacts"):
                    artifacts.extend(result.metadata["artifacts"])
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result.__dict__, ensure_ascii=False)})
        return AgentResult(task.id, "failed", summary=f"tool calling max steps exceeded ({self.max_steps})", evidence=evidence, failures=["max_tool_steps_exceeded"], started_at=started, finished_at=utc_now())
