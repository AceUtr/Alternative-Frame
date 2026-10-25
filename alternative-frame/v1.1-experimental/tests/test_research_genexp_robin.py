"""Research-domain acceptance of discovery artifacts, failures and provenance."""

import hashlib
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from domains.research_demo import ResearchDomainAdapter
from domains.research_tools import ResearchDiscoveryTool
from domains.research_tools.discovery import (
    REQUIRED_FIELDS, CandidateEvaluationError, build_protocol,
    generate_hypotheses, rank_candidates,
)
from domains.research_tools.discovery_tool import DISCOVERY_PATHS, discovery_report
from examples.research_task.generate_dataset import generate
from run_research_demo import run_demo


ROOT = Path(__file__).parents[1]


def fixture(tmp_path):
    workspace = tmp_path / "fixture"
    workspace.mkdir()
    for name in ("generate_dataset.py", "run_baseline.py", "run_improved.py", "verify_best.py"):
        shutil.copy(ROOT / "examples/research_task" / name, workspace)
    payload = generate(workspace / "data/dataset.json")
    evidence = {"train": payload["train"], "seed": payload["metadata"]["seed"],
                "dataset_version": payload["metadata"]["dataset_version"]}
    return workspace, payload, evidence


def read(workspace, name):
    return json.loads((workspace / DISCOVERY_PATHS[name]).read_text(encoding="utf-8"))


def inspect(tool):
    return tool.execute({"dataset_path": "data/dataset.json",
                         "output_path": "artifacts/dataset_summary.json"})


def test_generated_candidates_are_structured_and_reproducible(tmp_path):
    _, _, evidence = fixture(tmp_path)
    first = generate_hypotheses(evidence)
    assert first == generate_hypotheses(evidence)
    assert len(first) >= 2
    assert len({c["id"] for c in first}) == len(first)
    assert all(set(REQUIRED_FIELDS) <= c.keys() for c in first)
    assert {tuple(c["metadata"]["features_used"]) for c in first} == {("x1",), ("x1", "x2")}


def test_independent_ranking_is_order_invariant_and_has_fold_evidence(tmp_path):
    _, _, evidence = fixture(tmp_path)
    candidates = generate_hypotheses(evidence)
    ranked = rank_candidates(candidates, evidence)
    assert ranked == rank_candidates(list(reversed(candidates)), evidence)
    assert ranked[0]["metadata"]["features_used"] == ["x1", "x2"]
    for row in ranked:
        assert len(row["metadata"]["scores"]["fold_accuracies"]) == 5
        assert row["metadata"]["evaluation_basis"]
        assert row["metadata"]["comparisons"]
    assert ranked[0]["metadata"]["comparisons"][0]["winner_id"] == ranked[0]["id"]


def test_generator_scores_and_held_out_results_cannot_influence_evaluation(tmp_path):
    _, _, evidence = fixture(tmp_path)
    candidates = generate_hypotheses(evidence)
    expected = rank_candidates(candidates, evidence)
    candidates[0]["metadata"]["total_score"] = 999
    candidates[1]["metadata"]["total_score"] = -999
    evidence["test"] = [{"label": "arbitrary held-out result"}]
    actual = rank_candidates(candidates, evidence)
    assert actual == expected


@pytest.mark.parametrize("bad_score", [float("nan"), float("inf"), True, -0.1, 1.1])
def test_invalid_evaluator_scores_return_structured_failure(tmp_path, bad_score):
    _, _, evidence = fixture(tmp_path)
    with pytest.raises(CandidateEvaluationError) as error:
        rank_candidates(generate_hypotheses(evidence), evidence,
                        evaluator=lambda c, e: {"cv_accuracy": bad_score,
                                               "fold_accuracies": [bad_score] * 5,
                                               "feature_count": len(c["metadata"]["features_used"])})
    failure = error.value.result
    assert failure["status"] == "failed"
    assert failure["rankings"] == []
    assert failure["pairwise_comparisons"] == []
    assert failure["selected_id"] is None
    assert failure["error"]["category"] == "candidate_evaluation_failed"


def test_duplicate_candidates_are_not_silently_ranked(tmp_path):
    _, _, evidence = fixture(tmp_path)
    candidate = generate_hypotheses(evidence)[0]
    with pytest.raises(CandidateEvaluationError, match="unique"):
        rank_candidates([candidate, deepcopy(candidate)], evidence)


def test_exact_pairwise_ties_are_explicit_and_use_stable_id_order(tmp_path):
    _, _, evidence = fixture(tmp_path)
    first = generate_hypotheses(evidence)[0]
    second = deepcopy(first)
    first["id"], second["id"] = "hypothesis-a", "hypothesis-b"
    ranked = rank_candidates([second, first], evidence)
    assert [r["id"] for r in ranked] == ["hypothesis-a", "hypothesis-b"]
    assert ranked[0]["metadata"]["comparisons"][0]["winner_id"] is None
    assert all(r["metadata"]["pairwise_wins"] == 0 for r in ranked)


def test_insufficient_training_evidence_fails_without_ranking(tmp_path):
    _, _, evidence = fixture(tmp_path)
    candidates = generate_hypotheses(evidence)
    evidence["train"] = evidence["train"][:2]
    with pytest.raises(CandidateEvaluationError):
        rank_candidates(candidates, evidence)


def test_protocol_is_structured_and_requires_successful_selection(tmp_path):
    _, _, evidence = fixture(tmp_path)
    candidates = generate_hypotheses(evidence)
    with pytest.raises(ValueError, match="ranked"):
        build_protocol(candidates[0])
    ranked = rank_candidates(candidates, evidence)
    protocol = build_protocol(ranked[0])
    assert set(REQUIRED_FIELDS) <= protocol.keys()
    assert protocol["hypothesis_id"] == ranked[0]["id"]
    assert protocol["measurement"]["metric"] == "accuracy"
    assert protocol["constraints"]["selection_uses_test_data"] is False
    assert protocol["execution"]["verification_command"].startswith("python verify_best.py")


def test_discovery_tool_rejects_path_escape(tmp_path):
    workspace, _, _ = fixture(tmp_path)
    result = ResearchDiscoveryTool(workspace).execute(
        {"dataset_path": "../outside.json", "output_path": "artifacts/summary.json"})
    assert result.success is False
    assert "escapes workspace" in result.error


def test_failed_evaluation_removes_stale_protocol_and_has_no_fake_ranking(tmp_path, monkeypatch):
    workspace, _, _ = fixture(tmp_path)
    assert inspect(ResearchDiscoveryTool(workspace)).success
    monkeypatch.setenv("RESEARCH_EVALUATION_FAILURES", "always")
    result = inspect(ResearchDiscoveryTool(workspace))
    assert result.success is False
    assert result.metadata["evaluation_failure"]["rankings"] == []
    assert read(workspace, "ranking")["selected_id"] is None
    assert not (workspace / DISCOVERY_PATHS["protocol"]).exists()
    with pytest.raises((ValueError, OSError)):
        discovery_report(workspace)


@pytest.mark.parametrize("target", ["ranking", "protocol", "hypotheses"])
def test_tampered_discovery_evidence_is_rejected(tmp_path, target):
    workspace, _, _ = fixture(tmp_path)
    assert inspect(ResearchDiscoveryTool(workspace)).success
    doc = read(workspace, target)
    if target == "ranking":
        doc["rankings"][0]["metadata"]["total_score"] = 1.0
    elif target == "protocol":
        doc["hypothesis_id"] = "invented-candidate"
    else:
        doc["candidates"][0]["statement"] = "invented evidence"
    (workspace / DISCOVERY_PATHS[target]).write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        discovery_report(workspace)


def test_current_run_manifest_contract_report_and_reset_include_discovery(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTERNATIVE_FRAME_OUTPUT_DIR", str(tmp_path / "published"))
    workspace, _, _ = fixture(tmp_path)
    report = run_demo(workspace, tmp_path / "runs", "discovery-normal")
    assert report.status == "completed"
    assert report.state.phase == 2
    missing = report.state.phases[0].evaluation["missing_criteria"]
    assert "verification_metrics" in missing
    assert not any(m.startswith("research_") for m in missing)
    manifest = json.loads((tmp_path / "published/research/discovery-normal/manifest.json").read_text())
    entries = {e["path"]: e for e in manifest["entries"]}
    for name, relative in DISCOVERY_PATHS.items():
        data = (workspace / relative).read_bytes()
        assert entries[relative]["run_id"] == "discovery-normal"
        assert entries[relative]["sha256"] == hashlib.sha256(data).hexdigest()
        assert set(REQUIRED_FIELDS) <= json.loads(data).keys()
    text = (workspace / "artifacts/research_report.md").read_text(encoding="utf-8")
    assert "Hypothesis selection and protocol" in text
    assert "Independent verification: **passed**" in text
    assert all(Path(p).name in text for p in DISCOVERY_PATHS.values())
    expected = read(workspace, "ranking")
    rerun = run_demo(workspace, tmp_path / "runs", "discovery-second")
    assert rerun.status == "completed"
    assert read(workspace, "ranking") == expected
    assert len(read(workspace, "attempts")["attempts"]) == 1
    ResearchDomainAdapter().reset_workspace(workspace)
    assert all(not (workspace / p).exists() for p in DISCOVERY_PATHS.values())


def test_evaluator_failure_is_recorded_then_retried_by_existing_controller(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_EVALUATION_FAILURES", "1")
    monkeypatch.setenv("ALTERNATIVE_FRAME_OUTPUT_DIR", str(tmp_path / "published"))
    workspace, _, _ = fixture(tmp_path)
    report = run_demo(workspace, tmp_path / "runs", "discovery-retry")
    assert report.status == "completed"
    result = report.phase_reports[0].results["inspect_dataset"]
    assert result.attempts == 2
    assert result.tool_records[0]["success"] is False
    assert result.tool_records[0]["metadata"]["evaluation_failure"]["rankings"] == []
    assert result.tool_records[1]["success"] is True
    attempts = read(workspace, "attempts")["attempts"]
    assert [a["status"] for a in attempts] == ["failed", "success"]
    events = [json.loads(line) for line in
              (tmp_path / "runs/discovery-retry/events.jsonl").read_text().splitlines()]
    assert any(e["event"] == "task_retry_scheduled" and
               e["payload"]["task_id"] == "inspect_dataset" for e in events)


def test_persistent_evaluator_failure_cannot_complete_the_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_EVALUATION_FAILURES", "always")
    monkeypatch.setenv("ALTERNATIVE_FRAME_OUTPUT_DIR", str(tmp_path / "published"))
    workspace, _, _ = fixture(tmp_path)
    report = run_demo(workspace, tmp_path / "runs", "discovery-failed")
    assert report.status != "completed"
    assert read(workspace, "ranking")["status"] == "failed"
    assert read(workspace, "ranking")["rankings"] == []
    assert not (workspace / DISCOVERY_PATHS["protocol"]).exists()
    assert not (workspace / "artifacts/research_report.md").exists()
