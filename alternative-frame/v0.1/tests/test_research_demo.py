import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.acceptance import AcceptanceEvaluator
from core.domains import DomainRegistry
from core.long_horizon.contract_validator import ContractValidator
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from core.tools import ToolRegistry
from domains.research_demo import ResearchDomainAdapter
from domains.research_tools import DatasetInspector


PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "examples" / "research_task"


def _workspace(tmp_path):
    workspace = tmp_path / "research"
    workspace.mkdir(parents=True)
    shutil.copy(FIXTURE_ROOT / "generate_dataset.py", workspace)
    shutil.copy(FIXTURE_ROOT / "run_baseline.py", workspace)
    return workspace


def test_research_plan_is_valid_and_declares_domain_metadata():
    adapter = ResearchDomainAdapter()
    plan = adapter.build_plan("run an offline baseline")

    plan.validate()
    ContractValidator().validate(adapter.build_contract(plan.goal), plan.goal)
    domains = DomainRegistry([adapter])

    assert domains.get("research") is adapter
    assert adapter.name == "research"
    assert [task.id for task in plan.subtasks] == [
        "generate_dataset",
        "inspect_dataset",
        "run_baseline",
    ]
    for task in plan.subtasks:
        assert task.metadata["required_tools"]
        assert task.metadata["expected_outputs"]
        assert task.metadata["checks"]
        assert task.metadata["contract_criteria"]
        assert task.metadata["execution"]["tool"] in task.metadata["required_tools"]


def test_reset_workspace_is_repeatable_and_preserves_fixture_sources(tmp_path):
    workspace = _workspace(tmp_path)
    adapter = ResearchDomainAdapter()
    known_outputs = [
        workspace / "data/dataset.json",
        workspace / "artifacts/dataset_summary.json",
        workspace / "artifacts/baseline_metrics.json",
    ]
    for output in known_outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("stale", encoding="utf-8")
    sentinel = workspace / "artifacts/keep-me.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    adapter.reset_workspace(workspace)
    adapter.reset_workspace(workspace)

    assert all(not output.exists() for output in known_outputs)
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert (workspace / "generate_dataset.py").is_file()
    assert (workspace / "run_baseline.py").is_file()


def test_dataset_inspector_rejects_workspace_escape(tmp_path):
    result = DatasetInspector(tmp_path).execute(
        {
            "dataset_path": "../dataset.json",
            "output_path": "artifacts/summary.json",
        }
    )

    assert result.success is False
    assert "escapes workspace" in result.error


def test_adapter_passes_preflight_and_executes_real_baseline(tmp_path):
    workspace = _workspace(tmp_path)
    adapter = ResearchDomainAdapter()
    domains = DomainRegistry([adapter])
    tools, agents = adapter.configure(workspace)
    plan = adapter.build_plan("run an offline baseline")
    contract = adapter.build_contract(plan.goal)

    preflight = HarnessPreflightChecker().check(
        domains=domains,
        domain="research",
        plan=plan,
        agents=agents,
        tools=tools,
        workspace=workspace,
        contract=contract,
    )
    report = Orchestrator(
        agents,
        acceptance=AcceptanceEvaluator(workspace),
    ).run(plan, parallel=False)

    assert preflight.ready
    assert report.status == "success"
    metrics = json.loads(
        (workspace / "artifacts/baseline_metrics.json").read_text(encoding="utf-8")
    )
    assert metrics["experiment"] == "nearest_centroid_v1"
    assert metrics["seed"] == 1729
    assert 0.75 <= metrics["accuracy"] <= 0.9
    assert metrics["features_used"] == ["x1"]
    record = report.results["run_baseline"].tool_records[0]
    assert record["tool"] == "experiment_runner"
    assert record["success"] is True
    assert record["exit_code"] == 0
    assert record["metadata"]["metrics"]["accuracy"] == metrics["accuracy"]
    assert record["metadata"]["artifacts"] == [
        "artifacts/baseline_metrics.json"
    ]


def test_baseline_is_reproducible_with_fixed_seed(tmp_path):
    first = _workspace(tmp_path / "first")
    second = _workspace(tmp_path / "second")

    for workspace in (first, second):
        adapter = ResearchDomainAdapter()
        _, agents = adapter.configure(workspace, tools=ToolRegistry())
        report = Orchestrator(agents).run(
            adapter.build_plan("reproducibility check"),
            parallel=False,
        )
        assert report.status == "success"

    first_dataset = (first / "data/dataset.json").read_bytes()
    second_dataset = (second / "data/dataset.json").read_bytes()
    first_metrics = (first / "artifacts/baseline_metrics.json").read_bytes()
    second_metrics = (second / "artifacts/baseline_metrics.json").read_bytes()
    assert first_dataset == second_dataset
    assert first_metrics == second_metrics
