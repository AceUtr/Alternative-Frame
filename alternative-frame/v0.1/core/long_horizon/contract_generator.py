from __future__ import annotations

import json
from typing import Callable, Optional

from ..model_client import OpenAICompatibleClient
from ..models import Plan
from .acceptance_contract import AcceptanceContract, GoalCriterion
from .contract_validator import ContractValidationError, ContractValidator


class StructuredContractError(RuntimeError):
    pass


class StructuredGoalContractGenerator:
    """Generate a strict, validated final-goal acceptance contract before execution."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        validator: Optional[ContractValidator] = None,
        max_attempts: int = 2,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.client = client
        self.validator = validator or ContractValidator()
        self.max_attempts = max_attempts
        self.on_event = on_event

    def _emit(self, event: str, payload: dict) -> None:
        if not self.on_event:
            return
        try:
            self.on_event(event, payload)
        except Exception:
            # UI/logging failures must not alter contract validation behavior.
            pass

    def generate(self, goal: str, plan_hint: Optional[Plan] = None, domain: Optional[str] = None) -> AcceptanceContract:
        if not goal or not goal.strip():
            raise ValueError("goal cannot be empty")
        goal = goal.strip()
        messages = self._messages(goal, plan_hint, domain)
        last_error = "model did not return an acceptance contract"
        for attempt in range(1, self.max_attempts + 1):
            self._emit("contract_generation_started", {"attempt": attempt})
            content = ""
            try:
                response = self.client.chat(messages)
                content = response.get("content", "") if isinstance(response, dict) else str(response)
                payload = self._parse_json(content)
                contract = self._build_contract(goal, payload)
                self.validator.validate(contract, expected_goal=goal)
                self._emit(
                    "contract_generation_completed",
                    {
                        "attempt": attempt,
                        "criterion_count": len(contract.criteria),
                        "required_count": sum(item.required for item in contract.criteria),
                    },
                )
                return contract
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._emit("contract_validation_failed", {"attempt": attempt, "error": last_error})
                if attempt < self.max_attempts:
                    messages.extend(
                        [
                            {"role": "assistant", "content": content},
                            {
                                "role": "user",
                                "content": (
                                    f"The proposed contract was rejected: {last_error}. "
                                    "Return one corrected strict JSON object only."
                                ),
                            },
                        ]
                    )
        raise StructuredContractError(
            f"model failed to produce a valid goal contract after {self.max_attempts} attempts: {last_error}"
        )

    def _messages(self, goal, plan_hint, domain):
        hint = None
        if plan_hint:
            hint = {
                "plan_goal": plan_hint.goal,
                "final_acceptance": plan_hint.final_acceptance,
                "tasks": [
                    {
                        "id": task.id,
                        "role": task.role,
                        "description": task.description,
                        "expected_outputs": task.metadata.get("expected_outputs", []),
                        "checks": task.metadata.get("checks", []),
                    }
                    for task in plan_hint.subtasks
                ],
            }
        payload = {
            "original_user_goal": goal,
            "domain_hint": domain,
            "initial_plan_hint": hint,
            "instructions": [
                "Extract every explicit functional, test, documentation, quality, security, and metric requirement.",
                "Do not declare the task complete merely because Agents say success.",
                "Use file_exists only when a concrete relative artifact path is justified.",
                "Use command only for deterministic non-destructive verification commands.",
                "Use metric only with a concrete metric_name and numeric threshold stated or clearly implied by the goal.",
                "Use semantic for requirements needing evidence-backed qualitative review.",
                "Do not add unrelated product requirements or invent destructive commands.",
            ],
            "required_schema": {
                "goal_summary": "string",
                "criteria": [
                    {
                        "id": "unique_identifier",
                        "description": "one atomic completion requirement",
                        "check_type": "file_exists|command|metric|semantic|manual",
                        "required": "boolean",
                        "path": "relative path or null",
                        "command": "safe verification command or null",
                        "metric_name": "metric key or null",
                        "threshold": "number or null",
                    }
                ],
                "constraints": ["constraint copied or faithfully derived from the user goal"],
            },
        }
        return [
            {
                "role": "system",
                "content": (
                    "You generate the final acceptance contract for a long-horizon multi-agent task. "
                    "Return one strict JSON object only, without Markdown or prose. Preserve the user's intent, "
                    "separate atomic criteria, and remain conservative. The contract will be security-validated."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    @staticmethod
    def _parse_json(content):
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty contract response")
        payload = json.loads(content.strip())
        if not isinstance(payload, dict):
            raise ValueError("contract response must be a JSON object")
        return payload

    @staticmethod
    def _build_contract(goal, payload):
        summary = payload["goal_summary"]
        criteria_data = payload["criteria"]
        constraints = payload.get("constraints", [])
        if not isinstance(summary, str) or not isinstance(criteria_data, list) or not isinstance(constraints, list):
            raise ValueError("goal_summary, criteria, or constraints has an invalid type")
        criteria = []
        for item in criteria_data:
            criteria.append(
                GoalCriterion(
                    id=item["id"],
                    description=item["description"],
                    check_type=item["check_type"],
                    required=item.get("required", True),
                    path=item.get("path"),
                    command=item.get("command"),
                    metric_name=item.get("metric_name"),
                    threshold=item.get("threshold"),
                )
            )
        return AcceptanceContract(
            goal=goal,
            criteria=criteria,
            goal_summary=summary,
            constraints=constraints,
        )
