import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.domains import DomainRegistry
from core.long_horizon import DeterministicGlobalEvaluator, LongHorizonState
from core.models import Plan
from core.orchestrator import RunReport
from core.preflight import HarnessPreflightChecker
from core.tools import ToolRegistry
from domains.software_demo import DEFAULT_GOAL, EXACT_TEST_COMMAND, PythonAstRepairTool, SoftwareDomainAdapter
from run_software_demo import run_demo


def test_adapter_preflight_and_two_phase_contract(tmp_path):
    workspace = tmp_path / "fixture"
    adapter = SoftwareDomainAdapter()
    adapter.reset_workspace(workspace)
    tools, agents = adapter.configure(workspace)
    plan = adapter.build_plan(DEFAULT_GOAL)
    contract = adapter.build_contract(DEFAULT_GOAL)
    preflight = HarnessPreflightChecker().check(
        domains=DomainRegistry([adapter]), domain="software", plan=plan,
        agents=agents, tools=tools, workspace=workspace, contract=contract,
    )
    assert preflight.ready is True
    assert plan.subtasks[0].metadata["action"] == "diagnose"

    report = run_demo(workspace=workspace, runs_dir=tmp_path / "runs", run_id="software-test")
    assert report.status == "completed"
    assert report.state.phase == 2
    assert report.state.phases[0].evaluation["missing_criteria"] == [
        "repaired_source", "exact_tests", "report",
    ]
    assert report.state.phases[1].evaluation["completed"] is True
    assert report.state.total_tasks == 4
    assert (workspace / "artifacts" / "diagnosis.json").is_file()
    assert (workspace / "artifacts" / "software_report.md").is_file()
    assert "return a + b" in (workspace / "app.py").read_text(encoding="utf-8")
    events = (tmp_path / "runs" / "software-test" / "events.jsonl").read_text(encoding="utf-8")
    assert "global_hard_gate" in events
    assert "run_completed" in events


def test_reset_removes_stale_evidence_and_restores_bug(tmp_path):
    adapter = SoftwareDomainAdapter()
    adapter.reset_workspace(tmp_path)
    (tmp_path / "artifacts" / "stale.md").write_text("PASS", encoding="utf-8")
    (tmp_path / "app.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    adapter.reset_workspace(tmp_path)
    assert not (tmp_path / "artifacts" / "stale.md").exists()
    assert "return a - b" in (tmp_path / "app.py").read_text(encoding="utf-8")


def test_ast_repair_rejects_workspace_escape(tmp_path):
    tool = PythonAstRepairTool(tmp_path)
    result = ToolRegistry([tool]).execute(
        "python_ast_repair", {"path": "../outside.py", "function": "add", "operator": "add"}
    )
    assert result.success is False
    assert "escapes workspace" in result.error


def test_ast_repair_invalidates_stale_bytecode(tmp_path):
    adapter = SoftwareDomainAdapter()
    adapter.reset_workspace(tmp_path)
    cache = Path(importlib.util.cache_from_source(str(tmp_path / "app.py")))
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(b"stale bytecode")

    result = PythonAstRepairTool(tmp_path).execute(
        {"path": "app.py", "function": "add", "operator": "add"}
    )

    assert result.success is True
    assert not cache.exists()


def test_contract_rejects_files_without_current_run_provenance(tmp_path):
    adapter = SoftwareDomainAdapter()
    adapter.reset_workspace(tmp_path)
    contract = adapter.build_contract(DEFAULT_GOAL)
    state = LongHorizonState("stale", DEFAULT_GOAL, 2, 8)
    empty = RunReport(DEFAULT_GOAL, "success", {}, 0, "now", "now")
    evaluation = DeterministicGlobalEvaluator(contract, tmp_path).evaluate(
        state, Plan(DEFAULT_GOAL, []), empty
    )
    assert evaluation.completed is False
    assert set(evaluation.missing_criteria) == {"diagnosis", "repaired_source", "exact_tests", "report"}


def test_exact_test_command_is_recorded_with_real_exit_code(tmp_path):
    report = run_demo(workspace=tmp_path / "fixture", runs_dir=tmp_path / "runs", run_id="evidence")
    exact = [record for record in report.state.evidence_records
             if record.get("tool") == "test_runner"
             and record.get("arguments", {}).get("command") == EXACT_TEST_COMMAND]
    assert [record["exit_code"] for record in exact] == [1, 0]
    assert exact[-1]["success"] is True
