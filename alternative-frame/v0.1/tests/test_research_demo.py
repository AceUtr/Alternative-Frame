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
from domains.research_tools import DatasetInspector, MetricComparator, ResearchReportBuilder
from run_research_demo import run_demo


PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "examples" / "research_task"


def _workspace(tmp_path):
    workspace = tmp_path / "research"
    workspace.mkdir(parents=True)
    shutil.copy(FIXTURE_ROOT / "generate_dataset.py", workspace)
    shutil.copy(FIXTURE_ROOT / "run_baseline.py", workspace)
    shutil.copy(FIXTURE_ROOT / "run_improved.py", workspace)
    shutil.copy(FIXTURE_ROOT / "verify_best.py", workspace)
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
        "run_improved",
        "compare_experiments",
        "build_initial_report",
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
        workspace / "artifacts/improved_metrics.json",
        workspace / "artifacts/best_config.json",
        workspace / "artifacts/verification_metrics.json",
        workspace / "artifacts/comparison.png",
        workspace / "artifacts/research_report.md",
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
    assert (workspace / "run_improved.py").is_file()


def test_dataset_inspector_rejects_workspace_escape(tmp_path):
    result = DatasetInspector(tmp_path).execute(
        {
            "dataset_path": "../dataset.json",
            "output_path": "artifacts/summary.json",
        }
    )

    assert result.success is False
    assert "escapes workspace" in result.error


def _write_inspection_dataset(workspace, *, label=0, x1=0.1, provenance=True):
    metadata = {"dataset_version": "test-v1", "seed": 1729}
    if provenance:
        metadata["provenance"] = {
            "source": "synthetic_generated",
            "generator": "test",
            "license": "project_fixture",
        }
    payload = {
        "metadata": metadata,
        "train": [{"id": 1, "x1": x1, "x2": 0.2, "label": label}],
        "test": [{"id": 2, "x1": 0.3, "x2": 0.4, "label": 1}],
    }
    path = workspace / "data/dataset.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _inspect(workspace):
    return DatasetInspector(workspace).execute(
        {
            "dataset_path": "data/dataset.json",
            "output_path": "artifacts/summary.json",
            "required_fields": ["x1", "x2", "label"],
            "field_types": {
                "id": "integer",
                "x1": "number",
                "x2": "number",
                "label": "integer",
            },
            "allowed_labels": [0, 1],
            "required_provenance": ["source", "generator", "license"],
        }
    )


def test_dataset_inspector_records_provenance_and_content_hash(tmp_path):
    _write_inspection_dataset(tmp_path)

    result = _inspect(tmp_path)

    assert result.success is True
    assert result.metadata["dataset"]["provenance"]["source"] == "synthetic_generated"
    assert len(result.metadata["dataset"]["sha256"]) == 64


def test_dataset_inspector_rejects_invalid_field_type(tmp_path):
    _write_inspection_dataset(tmp_path, x1="not-a-number")

    result = _inspect(tmp_path)

    assert result.success is False
    assert "field x1 must be number" in result.error


def test_dataset_inspector_rejects_invalid_label(tmp_path):
    _write_inspection_dataset(tmp_path, label=7)

    result = _inspect(tmp_path)

    assert result.success is False
    assert "invalid label" in result.error


def test_dataset_inspector_requires_provenance(tmp_path):
    _write_inspection_dataset(tmp_path, provenance=False)

    result = _inspect(tmp_path)

    assert result.success is False
    assert "provenance" in result.error


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
    summary = json.loads(
        (workspace / "artifacts/dataset_summary.json").read_text(encoding="utf-8")
    )
    assert summary["provenance"]["generator"] == "generate_dataset.py"
    assert len(summary["sha256"]) == 64
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
    improved = json.loads(
        (workspace / "artifacts/improved_metrics.json").read_text(encoding="utf-8")
    )
    best = json.loads(
        (workspace / "artifacts/best_config.json").read_text(encoding="utf-8")
    )
    assert improved["accuracy"] > metrics["accuracy"]
    assert improved["features_used"] == ["x1", "x2"]
    assert best["best_experiment"] == improved["experiment"]
    assert best["best_score"] == improved["accuracy"]
    assert (workspace / "artifacts/comparison.png").read_bytes().startswith(
        b"\x89PNG\r\n\x1a\n"
    )
    initial_report = (workspace / "artifacts/research_report.md").read_text(
        encoding="utf-8"
    )
    assert "Independent verification: **pending**" in initial_report


def test_recovery_plan_independently_verifies_and_updates_report(tmp_path):
    workspace = _workspace(tmp_path)
    adapter = ResearchDomainAdapter()
    _, agents = adapter.configure(workspace)
    acceptance = AcceptanceEvaluator(workspace)
    orchestrator = Orchestrator(agents, acceptance=acceptance)

    initial = orchestrator.run(adapter.build_plan("two-phase research"), parallel=False)
    recovery_plan = adapter.build_recovery_plan("two-phase research")
    recovery_plan.validate()
    recovery = orchestrator.run(recovery_plan, parallel=False)

    assert initial.status == "success"
    assert recovery.status == "success"
    verification = json.loads(
        (workspace / "artifacts/verification_metrics.json").read_text(encoding="utf-8")
    )
    best = json.loads(
        (workspace / "artifacts/best_config.json").read_text(encoding="utf-8")
    )
    assert verification["accuracy"] == best["best_score"]
    assert verification["verified_experiment"] == best["best_experiment"]
    record = recovery.results["verify_best"].tool_records[0]
    assert record["exit_code"] == 0
    assert record["arguments"]["command"].startswith("python verify_best.py")
    final_report = (workspace / "artifacts/research_report.md").read_text(
        encoding="utf-8"
    )
    assert "Independent verification: **passed**" in final_report


def test_long_horizon_demo_rejects_phase_one_and_completes_phase_two(tmp_path):
    workspace = _workspace(tmp_path)
    runs = tmp_path / "runs"

    report = run_demo(workspace, runs, "research-test-run")

    assert report.status == "completed"
    assert report.state.phase == 2
    assert "verification_metrics" in report.state.phases[0].evaluation["missing_criteria"]
    assert "verification_command" in report.state.phases[0].evaluation["missing_criteria"]
    assert report.state.phases[1].status == "accepted"
    persisted = json.loads(
        (runs / "research-test-run/state.json").read_text(encoding="utf-8")
    )
    assert persisted["status"] == "completed"
    assert len(persisted["phases"]) == 2


def test_metric_comparator_rejects_workspace_escape(tmp_path):
    result = MetricComparator(tmp_path).execute(
        {
            "metric_files": ["../baseline.json", "artifacts/improved.json"],
            "primary_metric": "accuracy",
            "mode": "max",
            "output_path": "artifacts/best.json",
        }
    )

    assert result.success is False
    assert "escapes workspace" in result.error


def test_report_builder_rejects_workspace_escape(tmp_path):
    result = ResearchReportBuilder(tmp_path).execute(
        {
            "baseline_metrics_path": "../baseline.json",
            "improved_metrics_path": "artifacts/improved.json",
            "best_config_path": "artifacts/best.json",
            "verification_metrics_path": "artifacts/verification.json",
            "chart_path": "artifacts/comparison.png",
            "report_path": "artifacts/report.md",
        }
    )

    assert result.success is False
    assert "escapes workspace" in result.error


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
    first_improved = (first / "artifacts/improved_metrics.json").read_bytes()
    second_improved = (second / "artifacts/improved_metrics.json").read_bytes()
    first_best = (first / "artifacts/best_config.json").read_bytes()
    second_best = (second / "artifacts/best_config.json").read_bytes()
    assert first_dataset == second_dataset
    assert first_metrics == second_metrics
    assert first_improved == second_improved
    assert first_best == second_best
