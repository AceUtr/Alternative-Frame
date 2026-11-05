from __future__ import annotations

import json
import time
from typing import Callable, Mapping

from .agents import Agent
from .models import AgentResult, SubTask, utc_now
from .model_client import OpenAICompatibleClient
from .tools import ToolRegistry


class ToolCallingAgent(Agent):
    """LLM agent loop: model decides, registry executes, model observes."""

    def __init__(
        self,
        role: str,
        client: OpenAICompatibleClient,
        tools: ToolRegistry,
        system_prompt: str,
        max_steps: int = 20,
        on_tool_event: Callable[[str, dict], None] | None = None,
    ):
        self.role = role
        self.client = client
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.on_tool_event = on_tool_event

    def _emit_tool_event(self, event: str, payload: dict) -> None:
        if not self.on_tool_event:
            return
        try:
            self.on_tool_event(event, payload)
        except Exception:
            # Observability must never break task execution.
            pass

    def run(self, task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult:
        started = utc_now()
        protocol = (
            "\n\nTOOL PROTOCOL:\n"
            "1. Use tools only when an actual workspace action is necessary.\n"
            "2. After the requested artifacts exist and relevant checks pass, STOP calling tools.\n"
            "3. Return a concise final response with: completed work, artifact paths, checks run, and remaining risks.\n"
            "4. Never repeat the same tool call with identical arguments unless the previous result failed and you changed the plan."
        )
        task_contract = {
            "task_id": task.id,
            "role": task.role,
            "description": task.description,
            "required_tools": list(task.metadata.get("required_tools", [])),
            "expected_outputs": list(task.metadata.get("expected_outputs", [])),
            "acceptance_checks": list(task.metadata.get("checks", [])),
            "max_retries": task.max_retries,
        }
        payload = {
            "task_contract": task_contract,
            "dependencies": {key: value.summary for key, value in context.items()},
            "previous_attempt_artifacts": task.metadata.get("prior_artifacts", []),
            "previous_attempt_tool_results": task.metadata.get("prior_tool_results", []),
            "retry_feedback": task.metadata.get("retry_feedback"),
            "local_recovery_feedback": task.metadata.get("local_recovery_feedback"),
            "completion_rules": [
                "Create every declared expected output at its exact relative path.",
                "Execute every command check exactly as written and retain exit-code evidence.",
                "Do not claim completion from prose alone.",
            ],
        }
        messages = [
            {"role": "system", "content": self.system_prompt + protocol},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        evidence, artifacts, tool_records = [], [], []
        failed_call_counts = {}
        last_failed_signature = None
        for step in range(self.max_steps):
            try:
                response = self.client.chat(messages, tools=self.tools.schemas())
            except Exception as exc:
                return AgentResult(
                    task.id,
                    "failed",
                    summary="model request failed while executing this task",
                    artifacts=artifacts,
                    evidence=evidence,
                    tool_records=tool_records,
                    failures=[f"model_request_failed: {type(exc).__name__}: {exc}"],
                    started_at=started,
                    finished_at=utc_now(),
                )
            tool_calls = response.get("tool_calls", []) if isinstance(response, dict) else []
            if not tool_calls:
                content = response.get("content", "") if isinstance(response, dict) else str(response)
                if not content.strip() or response.get("_finish_reason") in ("length", "content_filter"):
                    return AgentResult(task.id, "failed", summary="model did not return a complete final response", artifacts=artifacts, evidence=evidence, tool_records=tool_records, failures=["incomplete_model_response"], started_at=started, finished_at=utc_now())
                return AgentResult(task.id, "success", summary=content, artifacts=artifacts, evidence=evidence + [f"model_step={step + 1}"], tool_records=tool_records, started_at=started, finished_at=utc_now())
            messages.append({"role": "assistant", "content": response.get("content", ""), "tool_calls": tool_calls})
            for call in tool_calls:
                name = call.get("function", {}).get("name", "")
                raw_args = call.get("function", {}).get("arguments", {})
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    if not isinstance(args, dict):
                        raise ValueError("tool arguments must be a JSON object")
                except (ValueError, TypeError) as exc:
                    args = {}
                    result_payload = {
                        "task_id": task.id,
                        "role": self.role,
                        "step": step + 1,
                        "tool": name,
                        "arguments": raw_args,
                        "success": False,
                        "error": f"invalid tool arguments: {exc}",
                        "output": "",
                        "duration_seconds": 0.0,
                    }
                    self._emit_tool_event("tool_finished", result_payload)
                    evidence.append(f"tool={name};success=False")
                    tool_records.append({"tool": name, "arguments": {}, "success": False, "error": result_payload["error"]})
                    messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result_payload, ensure_ascii=False)})
                    continue
                signature = name + ":" + json.dumps(args, ensure_ascii=False, sort_keys=True)
                event_payload = {
                    "task_id": task.id,
                    "role": self.role,
                    "step": step + 1,
                    "tool": name,
                    "arguments": args,
                }
                self._emit_tool_event("tool_started", event_payload)
                tool_started = time.perf_counter()
                result = self.tools.execute(name, args)
                result.duration_seconds = time.perf_counter() - tool_started
                if result.success:
                    failed_call_counts.clear()
                    last_failed_signature = None
                else:
                    if last_failed_signature != signature:
                        failed_call_counts.clear()
                    failed_call_counts[signature] = failed_call_counts.get(signature, 0) + 1
                    last_failed_signature = signature
                evidence.append(f"tool={name};success={result.success}")
                tool_records.append(
                    {
                        "tool": name,
                        "arguments": args,
                        "success": result.success,
                        "exit_code": result.exit_code,
                        "duration_seconds": result.duration_seconds,
                        "metadata": dict(result.metadata),
                        "output_excerpt": (result.output or result.error or "")[:1000],
                    }
                )
                if result.success and result.metadata.get("artifacts"):
                    artifacts.extend(result.metadata["artifacts"])
                self._emit_tool_event(
                    "tool_finished",
                    {
                        **event_payload,
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                        "exit_code": result.exit_code,
                        "duration_seconds": result.duration_seconds,
                    },
                )
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result.__dict__, ensure_ascii=False)})
                if failed_call_counts.get(signature, 0) >= 3:
                    return AgentResult(
                        task.id,
                        "failed",
                        summary="the same tool call failed three times without a changed request",
                        artifacts=artifacts,
                        evidence=evidence,
                        tool_records=tool_records,
                        failures=["repeated_tool_call", result.error or result.output[:300]],
                        started_at=started,
                        finished_at=utc_now(),
                    )
        return AgentResult(task.id, "failed", summary=f"tool calling max steps exceeded ({self.max_steps})", artifacts=artifacts, evidence=evidence, tool_records=tool_records, failures=["max_tool_steps_exceeded"], started_at=started, finished_at=utc_now())
