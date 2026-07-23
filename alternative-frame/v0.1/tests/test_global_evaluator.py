import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.agents import Agent, AgentRegistry
from core.long_horizon import (
    AcceptanceContract,
    EvidenceBundle,
    GoalCriterion,
    HardEvidenceGate,
    LongHorizonController,
    LongHorizonState,
    LongHorizonStore,
    StructuredGlobalEvaluator,
    DeterministicGlobalEvaluator,
)
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator


class JsonDecisionClient:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        return {"content": json.dumps(self.decisions.pop(0))}


def complete_decision():
    return {
        "completed": True,
        "reason": "implementation, exact test evidence, and README satisfy the final goal",
        "satisfied_criteria": ["source", "tests", "readme", "goal_coverage"],
        "missing_criteria": [],
        "failures": [],
        "next_focus": [],
        "evidence": ["artifact=src/module.py", "exit_code=0", "artifact=README.md"],
    }


def test_hard_gate_rejects_stale_file_without_run_provenance(tmp_path):
    (tmp_path / "README.md").write_text("stale", encoding="utf-8")
    contract = AcceptanceContract(
        "write README",
        [GoalCriterion("readme", "README exists", "file_exists", path="README.md")],
    )
    bundle = EvidenceBundle("success", {}, [], [], [])

    hard = HardEvidenceGate(tmp_path).evaluate(contract, bundle)

    assert hard.passed is False
    assert "no artifact provenance" in hard.failures[0]


def test_hard_gate_requires_the_exact_successful_command(tmp_path):
    contract = AcceptanceContract(
        "pass tests",
        [GoalCriterion("tests", "tests pass", "command", command="python -m unittest -v")],
    )
    wrong = EvidenceBundle(
        "success",
        {},
        [],
        [
            {
                "tool": "test_runner",
                "arguments": {"command": "pytest -q"},
                "success": True,
                "exit_code": 0,
                "metadata": {},
            }
        ],
        [],
    )
    exact = EvidenceBundle(
        "success",
        {},
        [],
        [
            {
                "tool": "test_runner",
                "arguments": {"command": "python -m unittest -v"},
                "success": True,
                "exit_code": 0,
                "metadata": {},
            }
        ],
        [],
    )

    assert HardEvidenceGate(tmp_path).evaluate(contract, wrong).passed is False
    assert HardEvidenceGate(tmp_path).evaluate(contract, exact).passed is True


class GoalDemoAgent(Agent):
    role = "worker"

    def __init__(self, workspace):
        self.workspace = Path(workspace)

    def run(self, task, context):
        if task.id == "source":
            path = self.workspace / "src" / "module.py"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def add(a, b): return a + b\n", encoding="utf-8")
            return AgentResult(task.id, "success", summary="source created", artifacts=["src/module.py"])
        if task.id == "tests":
            return AgentResult(
                task.id,
                "success",
                summary="tests passed",
                tool_records=[
                    {
                        "tool": "test_runner",
                        "arguments": {"command": "python -m unittest -v"},
                        "success": True,
                        "exit_code": 0,
                        "metadata": {"passed": True, "passed_count": 1, "failed_count": 0},
                        "output_excerpt": "Ran 1 test OK",
                    }
                ],
            )
        if task.id == "readme_missing":
            # Deliberately dishonest success: no file and no artifact evidence.
            return AgentResult(task.id, "success", summary="README completed")
        if task.id == "write_readme":
            (self.workspace / "README.md").write_text("# Demo\n", encoding="utf-8")
            return AgentResult(task.id, "success", summary="README created", artifacts=["README.md"])
        raise AssertionError(f"unexpected task: {task.id}")


def test_controller_continues_when_tasks_are_green_but_final_artifact_is_missing(tmp_path):
    contract = AcceptanceContract(
        "implement add, pass tests, and create README",
        [
            GoalCriterion("source", "source exists", "file_exists", path="src/module.py"),
            GoalCriterion("tests", "exact tests pass", "command", command="python -m unittest -v"),
            GoalCriterion("readme", "README exists", "file_exists", path="README.md"),
        ],
    )
    semantic_client = JsonDecisionClient([complete_decision()])
    evaluator_events = []
    evaluator = StructuredGlobalEvaluator(
        semantic_client,
        contract,
        tmp_path,
        on_event=lambda event, payload: evaluator_events.append((event, payload)),
    )
    registry = AgentRegistry()
    registry.register(GoalDemoAgent(tmp_path))
    initial_plan = Plan(
        "implement, test, and document",
        [
            SubTask("source", "worker", "create source"),
            SubTask("tests", "worker", "run tests", depends_on=["source"]),
            SubTask("readme_missing", "worker", "create README", depends_on=["tests"]),
        ],
    )
    recovery_plan = Plan(
        "create the missing README",
        [SubTask("write_readme", "worker", "create README with evidence")],
    )
    controller = LongHorizonController(
        Orchestrator(registry),
        lambda _state: initial_plan,
        LongHorizonStore(tmp_path / "runs"),
        evaluator=evaluator,
        replanner=lambda _state, _evaluation: recovery_plan,
        max_phases=3,
    )

    report = controller.run(contract.goal, run_id="goal-proof")

    assert report.status == "completed"
    assert report.state.phase == 2
    assert report.state.phases[0].report_status == "success"
    assert report.state.phases[0].evaluation["completed"] is False
    assert report.state.phases[0].evaluation["missing_criteria"] == ["readme"]
    assert report.state.phases[1].evaluation["completed"] is True
    assert semantic_client.calls == 1
    assert len(report.state.evidence_records) == 1
    assert (tmp_path / "README.md").is_file()
    hard_events = [payload for event, payload in evaluator_events if event == "global_hard_gate"]
    assert [event["passed"] for event in hard_events] == [False, True]


def test_semantic_evaluator_fails_closed_on_invalid_model_output(tmp_path):
    contract = AcceptanceContract("semantic goal", [])
    client = JsonDecisionClient([{"completed": "yes"}, {"completed": "yes"}])
    evaluator = StructuredGlobalEvaluator(client, contract, tmp_path)
    state = LongHorizonState("run", contract.goal, max_phases=2, max_total_tasks=5)
    registry = AgentRegistry()
    registry.register(GoalDemoAgent(tmp_path))
    report = Orchestrator(registry).run(Plan("phase", [SubTask("readme_missing", "worker", "claim")]))

    evaluation = evaluator.evaluate(state, Plan("phase", []), report)

    assert evaluation.completed is False
    assert evaluation.missing_criteria == ["semantic_goal_coverage"]
    assert client.calls == 2


def test_deterministic_global_evaluator_rejects_green_tasks_with_missing_contract_files(tmp_path):
    contract = AcceptanceContract(
        "deliver files and tests",
        [
            GoalCriterion("source", "source exists", "file_exists", path="retry_demo/word_counter.py"),
            GoalCriterion("tests", "tests exist", "file_exists", path="retry_demo/test_word_counter.py"),
            GoalCriterion("command", "tests pass", "command", command="python -m unittest -v"),
        ],
    )
    (tmp_path / "retry_demo").mkdir()
    (tmp_path / "retry_demo" / "word_counter.py").write_text("pass\n", encoding="utf-8")
    state = LongHorizonState("run", contract.goal, 3, 20, artifacts=["retry_demo/word_counter.py"])
    registry = AgentRegistry()
    registry.register(GoalDemoAgent(tmp_path))
    report = Orchestrator(registry).run(Plan("claim success", [SubTask("readme_missing", "worker", "claim")]))

    result = DeterministicGlobalEvaluator(contract, tmp_path).evaluate(state, Plan("phase", []), report)

    assert result.completed is False
    assert result.missing_criteria == ["tests", "command"]


def test_artifact_uri_cannot_prove_a_real_contract_file(tmp_path):
    (tmp_path / "review").write_text("exists", encoding="utf-8")
    contract = AcceptanceContract(
        "real output",
        [GoalCriterion("review", "review exists", "file_exists", path="review")],
    )
    bundle = EvidenceBundle("success", {}, ["artifact://review"], [], [])

    result = HardEvidenceGate(tmp_path).evaluate(contract, bundle)

    assert result.passed is False
    assert "no artifact provenance" in result.failures[0]


def test_resume_revokes_historical_false_completion_and_runs_recovery(tmp_path):
    contract = AcceptanceContract(
        "create required output",
        [GoalCriterion("required", "required file exists", "file_exists", path="required.txt")],
    )
    state = LongHorizonState(
        "false-positive", contract.goal, 3, 10,
        status="completed", phase=1, total_tasks=1,
        acceptance_contract=contract.to_dict(),
        last_evaluation=GoalEvaluation(True, "legacy phase status").to_dict(),
    )
    store = LongHorizonStore(tmp_path / "runs")
    store.save(state)

    class RecoveryAgent(Agent):
        role = "worker"

        def run(self, task, context):
            (tmp_path / "required.txt").write_text("done", encoding="utf-8")
            return AgentResult(task.id, "success", artifacts=["required.txt"])

    registry = AgentRegistry()
    registry.register(RecoveryAgent())
    controller = LongHorizonController(
        Orchestrator(registry),
        lambda _state: Plan("unused", []),
        store,
        evaluator=DeterministicGlobalEvaluator(contract, tmp_path),
        replanner=lambda _state, _evaluation: Plan(
            "repair", [SubTask("repair", "worker", "create required output")]
        ),
        acceptance_contract=contract.to_dict(),
    )

    report = controller.run(contract.goal, run_id="false-positive", resume=True)

    assert report.status == "completed"
    assert report.state.phase == 2
    assert report.state.last_evaluation["satisfied_criteria"] == ["required"]
    events = (tmp_path / "runs" / "false-positive" / "events.jsonl").read_text(encoding="utf-8")
    assert "completed_run_audit_failed" in events
