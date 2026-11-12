from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.agents import AgentRegistry, DeterministicAgent
from core.long_horizon import (
    AcceptanceContract,
    GoalCriterion,
    GoalEvaluation,
    LongHorizonController,
    LongHorizonStore,
)
from core.long_horizon.runtime_changes import RuntimeChangeInbox, submit_change
from core.long_horizon.runtime_change_acceptance import run_experiment, verify_run
from core.models import Plan, SubTask
from core.orchestrator import Orchestrator


def _contract(goal: str) -> AcceptanceContract:
    return AcceptanceContract(
        goal=goal,
        goal_summary=goal,
        criteria=[GoalCriterion("initial", "Initial acceptance condition", "semantic")],
    )


def _request(run_id: str, *, revision: int = 1, check_type: str = "semantic", path: str | None = None) -> dict:
    criterion = {
        "id": "runtime_requirement",
        "description": "The dynamically added requirement is satisfied.",
        "check_type": check_type,
        "required": True,
    }
    if path is not None:
        criterion["path"] = path
    return {
        "schema_version": 1,
        "run_id": run_id,
        "request_id": "change-one",
        "base_revision": revision,
        "description": "Add a runtime acceptance condition.",
        "add_criteria": [criterion],
        "add_constraints": [],
    }


def _save_running_state(root: Path, run_id: str, contract: AcceptanceContract):
    store = LongHorizonStore(root)
    from core.long_horizon.state import LongHorizonState

    state = LongHorizonState(
        run_id=run_id,
        goal=contract.goal,
        max_phases=3,
        max_total_tasks=10,
        status="running",
        acceptance_contract=contract.to_dict(),
    )
    store.save(state)
    return store


def test_submit_change_validates_revision_and_safe_contract_paths(tmp_path):
    goal = "deliver a report"
    contract = _contract(goal)
    store = _save_running_state(tmp_path, "submit-run", contract)
    run_dir = store.run_dir("submit-run")

    accepted = submit_change(run_dir, _request("submit-run"))

    assert accepted.is_file()
    assert json.loads(accepted.read_text(encoding="utf-8"))["base_revision"] == 1
    with pytest.raises(ValueError, match="base_revision"):
        submit_change(run_dir, _request("submit-run", revision=0))
    with pytest.raises(ValueError, match="unsafe or missing relative path"):
        submit_change(run_dir, _request("submit-run", check_type="file_exists", path="../outside.txt"))
    assert len(list((run_dir / "runtime_changes" / "pending").glob("*.json"))) == 1


def test_submit_change_rejects_wrong_run_and_terminal_state(tmp_path):
    contract = _contract("deliver a report")
    store = _save_running_state(tmp_path, "terminal-run", contract)
    run_dir = store.run_dir("terminal-run")

    with pytest.raises(ValueError, match="run_id"):
        submit_change(run_dir, _request("another-run"))

    state = store.load("terminal-run")
    state.status = "completed"
    store.save(state)
    with pytest.raises(ValueError, match="currently running"):
        submit_change(run_dir, _request("terminal-run"))


def test_change_arriving_during_final_evaluation_revises_before_phase_commit(tmp_path):
    goal = "produce and verify a report"
    contract = _contract(goal)
    runs_root = tmp_path / "runs"
    store = LongHorizonStore(runs_root)
    run_id = "runtime-race"
    inbox = RuntimeChangeInbox(store.run_dir(run_id) / "runtime_changes")

    class InjectingEvaluator:
        def __init__(self):
            self.contract = contract
            self.calls = []
            self.injected = False

        def update_contract(self, updated):
            self.contract = updated

        def evaluate(self, state, plan, report):
            self.calls.append((plan.goal, state.contract_revision, len(self.contract.criteria)))
            if not self.injected:
                self.injected = True
                submit_change(store.run_dir(run_id), _request(run_id))
                return GoalEvaluation(True, "stale pre-change acceptance")
            if plan.goal == "initial work":
                assert len(self.contract.criteria) == 2
                return GoalEvaluation(False, "new runtime requirement remains", missing_criteria=["runtime_requirement"], next_focus=["satisfy runtime requirement"])
            return GoalEvaluation(True, "both original and runtime requirements passed")

    evaluator = InjectingEvaluator()
    registry = AgentRegistry()
    registry.register(DeterministicAgent("worker"))
    controller = LongHorizonController(
        Orchestrator(registry),
        lambda _state: Plan("initial work", [SubTask("initial", "worker", "produce baseline")]),
        store,
        evaluator=evaluator,
        replanner=lambda _state, _evaluation: Plan("finish added requirement", [SubTask("finish", "worker", "satisfy added requirement")]),
        max_phases=3,
        max_total_tasks=10,
        acceptance_contract=contract.to_dict(),
        runtime_change_inbox=inbox,
    )

    report = controller.run(goal, run_id=run_id)

    assert report.status == "completed"
    assert report.state.contract_revision == 2
    assert [phase.contract_revision for phase in report.state.phases] == [2, 2]
    assert [phase.status for phase in report.state.phases] == ["incomplete", "accepted"]
    assert report.state.phases[0].evaluation["completed"] is False
    assert report.state.last_evaluation["reason"] == "both original and runtime requirements passed"
    events = [json.loads(line) for line in store.run_dir(run_id).joinpath("events.jsonl").read_text(encoding="utf-8").splitlines()]
    finished = [item["payload"] for item in events if item["event"] == "phase_finished"]
    completed = [item["payload"] for item in events if item["event"] == "run_completed"]
    assert [item["contract_revision"] for item in finished] == [2, 2]
    assert len(completed) == 1 and completed[0]["contract_revision"] == 2


def test_phase_record_reads_legacy_state_without_contract_revision(tmp_path):
    from core.long_horizon.state import LongHorizonState

    payload = {
        "run_id": "legacy-phase",
        "goal": "legacy goal",
        "max_phases": 1,
        "max_total_tasks": 1,
        "phases": [{
            "number": 1,
            "plan_goal": "old phase",
            "task_ids": [],
            "status": "accepted",
            "report_status": "success",
            "evaluation": {"completed": True, "reason": "legacy"},
        }],
    }

    restored = LongHorizonState.from_dict(payload)

    assert restored.phases[0].contract_revision == 1


@pytest.mark.parametrize("delay", [0, 0.05, 0.25])
def test_external_process_runtime_change_acceptance_evidence(tmp_path, delay):
    run_id = f"external-change-e2e-{str(delay).replace('.', '-')}"
    summary = run_experiment(tmp_path / "evidence", run_id=run_id, injection_delay_seconds=delay)
    run_dir = tmp_path / "evidence" / run_id

    assert summary["verification_passed"] is True
    assert summary["network_scope"] == "single_host_external_process_control"
    assert summary["checks"]["injection_between_phase_tasks"] is True
    assert summary["checks"]["first_phase_rejected_stale_completion"] is True
    assert summary["checks"]["controller_replanned_second_phase"] is True
    assert summary["checks"]["baseline_retained"] is True
    assert verify_run(run_dir)["passed"] is True
