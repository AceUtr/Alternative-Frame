import subprocess
import importlib.util
import py_compile

from core.acceptance import AcceptanceEvaluator
from core.domains import DomainRegistry
from core.local_recovery import LocalDAGRecoveryController
from core.long_horizon import EvidenceBundle, HardEvidenceGate
from core.models import AgentResult, SubTask
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from domains.software_demo import PYTEST_COMMAND, SoftwareDomainAdapter


def configure_software(tmp_path):
    workspace = tmp_path / "workspace"
    adapter = SoftwareDomainAdapter()
    adapter.reset_workspace(workspace)
    tools, agents = adapter.configure(workspace)
    goal = "Repair the supplied buggy application and prove the exact test command passes"
    plan = adapter.build_plan(goal)
    contract = adapter.build_contract(goal)
    return adapter, workspace, tools, agents, plan, contract


def failed_contract_criteria(report):
    return [result.criterion_id for result in report.results if result.status == "failed"]


def write_report_artifact(workspace):
    report = workspace / "artifacts" / "software_report.md"
    report.write_text("# Report\n", encoding="utf-8")


def test_adapter_passes_preflight(tmp_path):
    adapter, workspace, tools, agents, plan, contract = configure_software(tmp_path)
    report = HarnessPreflightChecker().check(
        domains=DomainRegistry([adapter]),
        domain="software",
        plan=plan,
        agents=agents,
        tools=tools,
        workspace=workspace,
        contract=contract,
    )

    assert report.ready
    assert "developer" in agents.roles()
    assert "test_runner" in tools.names()


def test_fixture_reset_starts_from_real_failing_bug(tmp_path):
    _adapter, workspace, _tools, _agents, _plan, _contract = configure_software(tmp_path)

    assert "return b - a" in (workspace / "app.py").read_text(encoding="utf-8")
    completed = subprocess.run(
        PYTEST_COMMAND.split(),
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode != 0


def test_file_editor_rejects_workspace_escape(tmp_path):
    _adapter, _workspace, tools, _agents, _plan, _contract = configure_software(tmp_path)

    result = tools.execute(
        "file_editor",
        {"action": "write", "path": "../escape.txt", "content": "no"},
    )

    assert result.success is False
    assert "escapes workspace" in result.error


def test_software_plan_repairs_bug_and_generates_current_evidence(tmp_path):
    _adapter, workspace, tools, agents, plan, _contract = configure_software(tmp_path)
    for task in plan.subtasks:
        if task.id == "implement_fix":
            task.metadata["fault_scenario"] = "retry-once"
    events = []
    report = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
        on_event=lambda event, task, result=None: events.append((event, task.id, result)),
    ).run(plan)

    assert report.status == "success"
    assert report.results["implement_fix"].attempts == 2
    assert any(event == "task_retry_scheduled" and task_id == "implement_fix" for event, task_id, _ in events)
    assert any(
        record["tool"] == "retry_feedback"
        and isinstance(record["arguments"], dict)
        for record in report.results["implement_fix"].tool_records
    )
    assert "return a + b" in (workspace / "app.py").read_text(encoding="utf-8")
    assert (workspace / "artifacts" / "software_report.md").is_file()
    assert (workspace / "artifacts" / "test_log.txt").is_file()


def test_retry_once_clears_equal_length_stale_bytecode(tmp_path):
    _adapter, workspace, _tools, agents, plan, _contract = configure_software(tmp_path)
    stale_source = "def add(a, b):\n    return a * b\n"
    (workspace / "app.py").write_text(stale_source, encoding="utf-8")
    py_compile.compile(
        str(workspace / "app.py"),
        cfile=importlib.util.cache_from_source(str(workspace / "app.py")),
    )
    for task in plan.subtasks:
        if task.id == "implement_fix":
            task.metadata["fault_scenario"] = "retry-once"

    report = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
    ).run(plan)

    assert report.status == "success"
    assert report.results["implement_fix"].attempts == 2
    assert "return a + b" in (workspace / "app.py").read_text(encoding="utf-8")


def test_local_recovery_scenario_freezes_prior_nodes_and_recovers_impacted_subgraph(tmp_path):
    _adapter, workspace, tools, agents, plan, _contract = configure_software(tmp_path)
    for task in plan.subtasks:
        if task.id == "run_targeted_tests":
            task.metadata["fault_scenario"] = "local-recovery"

    orchestrator = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
    )
    outcome = LocalDAGRecoveryController(orchestrator, max_cycles=1).run(plan, task_budget=12)

    assert outcome.report.status == "success"
    assert outcome.cycles == 1
    assert outcome.impacts[0]["frozen"] == [
        "inspect_requirements",
        "inspect_repository",
        "diagnose_failure",
        "implement_fix",
    ]
    assert outcome.impacts[0]["impacted"] == ["run_targeted_tests", "build_change_report"]
    assert outcome.report.results["run_targeted_tests"].status == "success"
    assert outcome.report.results["build_change_report"].status == "success"
    assert (workspace / "artifacts" / "software_report.md").is_file()


def test_stale_report_file_without_run_provenance_is_rejected(tmp_path):
    _adapter, workspace, _tools, _agents, _plan, _contract = configure_software(tmp_path)
    (workspace / "artifacts" / "software_report.md").write_text("stale", encoding="utf-8")
    task = SubTask(
        "build_change_report",
        "reporter",
        "write report",
        metadata={
            "expected_outputs": ["artifacts/software_report.md"],
            "checks": [
                {
                    "id": "software_report_exists",
                    "check_type": "file_exists",
                    "path": "artifacts/software_report.md",
                }
            ],
        },
    )

    result = AgentResult("build_change_report", "success", summary="old report exists")
    acceptance = AcceptanceEvaluator(workspace).evaluate(task, result)

    assert acceptance.passed is False
    assert "missing_run_provenance" in acceptance.failures[0]


def test_contract_rejects_agent_prose_without_tool_evidence(tmp_path):
    _adapter, workspace, _tools, _agents, _plan, contract = configure_software(tmp_path)
    bundle = EvidenceBundle(
        report_status="success",
        task_results={
            "claim": {
                "status": "success",
                "summary": "Agent says the source was fixed and tests passed.",
                "artifacts": [],
                "failures": [],
            }
        },
        artifacts=[],
        tool_records=[],
        failures=[],
    )

    report = HardEvidenceGate(workspace).evaluate(contract, bundle)

    assert report.passed is False
    assert "pytest_pass" in failed_contract_criteria(report)


def test_contract_rejects_successful_but_wrong_test_command(tmp_path):
    _adapter, workspace, _tools, _agents, _plan, contract = configure_software(tmp_path)
    write_report_artifact(workspace)
    bundle = EvidenceBundle(
        report_status="success",
        task_results={},
        artifacts=["app.py", "test_app.py", "artifacts/software_report.md"],
        tool_records=[
            {
                "tool": "test_runner",
                "arguments": {"command": "python -m pytest -q"},
                "success": True,
                "exit_code": 0,
                "metadata": {"passed": True},
            }
        ],
        failures=[],
    )

    report = HardEvidenceGate(workspace).evaluate(contract, bundle)

    assert report.passed is False
    assert "pytest_pass" in failed_contract_criteria(report)
    assert any("exact command" in failure for failure in report.failures)


def test_contract_rejects_exact_test_command_with_nonzero_exit(tmp_path):
    _adapter, workspace, _tools, _agents, _plan, contract = configure_software(tmp_path)
    write_report_artifact(workspace)
    bundle = EvidenceBundle(
        report_status="success",
        task_results={},
        artifacts=["app.py", "test_app.py", "artifacts/software_report.md"],
        tool_records=[
            {
                "tool": "test_runner",
                "arguments": {"command": PYTEST_COMMAND},
                "success": False,
                "exit_code": 1,
                "metadata": {"passed": False},
            }
        ],
        failures=[],
    )

    report = HardEvidenceGate(workspace).evaluate(contract, bundle)

    assert report.passed is False
    assert "pytest_pass" in failed_contract_criteria(report)


def test_contract_rejects_existing_regression_test_without_run_provenance(tmp_path):
    _adapter, workspace, _tools, _agents, _plan, contract = configure_software(tmp_path)
    write_report_artifact(workspace)
    bundle = EvidenceBundle(
        report_status="success",
        task_results={},
        artifacts=["app.py", "artifacts/software_report.md"],
        tool_records=[
            {
                "tool": "test_runner",
                "arguments": {"command": PYTEST_COMMAND},
                "success": True,
                "exit_code": 0,
                "metadata": {"passed": True},
            }
        ],
        failures=[],
    )

    report = HardEvidenceGate(workspace).evaluate(contract, bundle)

    assert report.passed is False
    assert "regression_tests_exist" in failed_contract_criteria(report)
    assert any("test_app.py" in failure and "no artifact provenance" in failure for failure in report.failures)
