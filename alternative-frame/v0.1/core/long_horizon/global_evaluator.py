from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

from ..model_client import OpenAICompatibleClient
from ..models import Plan
from ..orchestrator import RunReport
from .acceptance_contract import AcceptanceContract
from .evaluator import GoalEvaluation
from .evidence import EvidenceBundle, HardEvidenceGate
from .state import LongHorizonState


class StructuredGlobalEvaluator:
    """Hard evidence gates plus conservative structured semantic evaluation."""

    def __init__(
        self,
        client: OpenAICompatibleClient,
        contract: AcceptanceContract,
        workspace,
        max_attempts: int = 2,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.client = client
        self.contract = contract
        self.hard_gate = HardEvidenceGate(workspace)
        self.max_attempts = max_attempts
        self.on_event = on_event

    def evaluate(self, state: LongHorizonState, plan: Plan, report: RunReport) -> GoalEvaluation:
        bundle = EvidenceBundle.collect(state, report)
        hard = self.hard_gate.evaluate(self.contract, bundle)
        passed_ids = [result.criterion_id for result in hard.results if result.status == "passed"]
        missing_ids = [result.criterion_id for result in hard.results if result.status == "failed"]
        hard_evidence = [
            f"{result.criterion_id}: {item}"
            for result in hard.results
            for item in result.evidence
        ]
        self._emit(
            "global_hard_gate",
            {
                "passed": hard.passed,
                "passed_count": len(passed_ids),
                "missing_count": len(missing_ids),
                "failures": hard.failures,
                "results": [item.to_dict() for item in hard.results],
            },
        )
        if not hard.passed:
            return GoalEvaluation(
                completed=False,
                reason="deterministic global acceptance gates did not pass",
                satisfied_criteria=passed_ids,
                missing_criteria=missing_ids,
                failures=list(hard.failures),
                next_focus=[f"satisfy hard criterion: {item}" for item in missing_ids]
                or ["repair failed phase tasks"],
                evidence=hard_evidence,
            )

        messages = self._messages(state, plan, bundle, hard.to_dict())
        last_error = "semantic evaluator did not return a decision"
        for attempt in range(1, self.max_attempts + 1):
            self._emit("global_semantic_started", {"attempt": attempt, "phase": state.phase + 1})
            try:
                response = self.client.chat(messages)
                content = response.get("content", "") if isinstance(response, dict) else str(response)
                decision = self._parse_decision(content)
                completed = decision["completed"] is True
                result = GoalEvaluation(
                    completed=completed,
                    reason=decision["reason"],
                    satisfied_criteria=list(dict.fromkeys(passed_ids + decision["satisfied_criteria"])),
                    missing_criteria=decision["missing_criteria"],
                    failures=decision["failures"],
                    next_focus=decision["next_focus"],
                    evidence=list(dict.fromkeys(hard_evidence + decision["evidence"])),
                )
                if not completed and not result.next_focus:
                    result.next_focus = ["resolve semantic acceptance gaps"]
                self._emit(
                    "global_semantic_completed",
                    {
                        "attempt": attempt,
                        "completed": result.completed,
                        "missing_criteria": result.missing_criteria,
                    },
                )
                return result
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._emit("global_semantic_failed", {"attempt": attempt, "error": last_error})
                if attempt < self.max_attempts:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"The previous evaluation was invalid: {last_error}. "
                                "Return one corrected strict JSON object only."
                            ),
                        }
                    )

        # Fail closed: unavailable or malformed semantic judgment can never mark completion.
        return GoalEvaluation(
            completed=False,
            reason="semantic global evaluation unavailable or invalid",
            satisfied_criteria=passed_ids,
            missing_criteria=["semantic_goal_coverage"],
            failures=[last_error],
            next_focus=["retry semantic global evaluation"],
            evidence=hard_evidence,
        )

    def _messages(self, state, plan, bundle, hard_report):
        compact_records = []
        for record in bundle.tool_records[-50:]:
            compact_records.append(
                {
                    "tool": record.get("tool"),
                    "arguments": record.get("arguments", {}),
                    "success": record.get("success"),
                    "exit_code": record.get("exit_code"),
                    "metadata": record.get("metadata", {}),
                    "output_excerpt": str(record.get("output_excerpt", ""))[:500],
                }
            )
        payload = {
            "final_goal": state.goal,
            "completed_phase_count": state.phase,
            "current_phase_goal": plan.goal,
            "acceptance_contract": self.contract.to_dict(),
            "hard_gate": hard_report,
            "task_results": bundle.task_results,
            "artifacts_with_run_provenance": bundle.artifacts,
            "tool_evidence": compact_records,
            "prior_decisions": state.decisions[-10:],
            "required_response": {
                "completed": "boolean",
                "reason": "string",
                "satisfied_criteria": ["criterion or goal requirement"],
                "missing_criteria": ["missing goal requirement"],
                "failures": ["concrete failure"],
                "next_focus": ["specific next-stage objective"],
                "evidence": ["evidence identifier from supplied data"],
            },
        }
        return [
            {
                "role": "system",
                "content": (
                    "You are a conservative final-goal evaluator for a long-horizon multi-agent system. "
                    "Hard-gate results cannot be overridden. Judge whether the user's entire final goal is "
                    "satisfied by supplied, run-provenanced evidence. Do not accept agent claims without evidence. "
                    "Return one strict JSON object only, without Markdown or prose. When uncertain, set completed=false."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]

    @staticmethod
    def _parse_decision(content: str) -> Dict:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty semantic evaluation")
        decision = json.loads(content.strip())
        if not isinstance(decision, dict) or not isinstance(decision.get("completed"), bool):
            raise ValueError("semantic evaluation must be a JSON object with boolean completed")
        if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
            raise ValueError("semantic evaluation reason must be a non-empty string")
        for field in (
            "satisfied_criteria",
            "missing_criteria",
            "failures",
            "next_focus",
            "evidence",
        ):
            value = decision.get(field)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"semantic evaluation field {field} must be a list of strings")
        return decision

    def _emit(self, event: str, payload: dict) -> None:
        if not self.on_event:
            return
        try:
            self.on_event(event, payload)
        except Exception:
            pass


class DeterministicGlobalEvaluator:
    """Contract-level evaluator for runs that have no semantic model client.

    It deliberately fails closed when required criteria need semantic review.
    A green phase report alone is never sufficient to complete a contracted run.
    """

    def __init__(self, contract: AcceptanceContract, workspace, on_event=None):
        self.contract = contract
        self.hard_gate = HardEvidenceGate(workspace)
        self.on_event = on_event

    def evaluate(self, state: LongHorizonState, plan: Plan, report: RunReport) -> GoalEvaluation:
        bundle = EvidenceBundle.collect(state, report)
        hard = self.hard_gate.evaluate(self.contract, bundle)
        passed = [item.criterion_id for item in hard.results if item.status == "passed"]
        failed = [item.criterion_id for item in hard.results if item.status == "failed"]
        deferred = [
            item.criterion_id
            for item in hard.results
            if item.status == "deferred"
            and next((criterion.required for criterion in self.contract.criteria if criterion.id == item.criterion_id), True)
        ]
        evidence = [
            f"{item.criterion_id}: {proof}"
            for item in hard.results
            for proof in item.evidence
        ]
        missing = list(dict.fromkeys(failed + deferred))
        completed = hard.passed and not deferred
        failures = list(hard.failures)
        if deferred:
            failures.append(f"required criteria need semantic evaluation: {deferred}")
        self._emit("global_hard_gate", {
            "passed": completed,
            "passed_count": len(passed),
            "missing_count": len(missing),
            "failures": failures,
            "results": [item.to_dict() for item in hard.results],
        })
        return GoalEvaluation(
            completed=completed,
            reason=(
                "all deterministic contract acceptance gates passed"
                if completed
                else "deterministic contract acceptance gates did not pass"
            ),
            satisfied_criteria=passed,
            missing_criteria=missing,
            failures=failures,
            next_focus=[f"satisfy contract criterion: {item}" for item in missing],
            evidence=evidence,
        )

    def _emit(self, event, payload):
        if self.on_event:
            try:
                self.on_event(event, payload)
            except Exception:
                pass
