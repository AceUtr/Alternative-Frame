import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.model_client import ModelConfig, OpenAICompatibleClient
from core.models import AgentResult
from core.orchestrator import RunReport
from ui import load_api_usage_totals, save_api_usage_evidence, save_standard_run_evidence


def test_ui_writes_traceable_usage_without_credentials(tmp_path):
    config = ModelConfig("https://example.test/v1", "not-to-save", "test-model")
    client = OpenAICompatibleClient(config)
    path = tmp_path / "run" / "api_usage.json"

    save_api_usage_evidence(path, "run-1", client, config, "paused")
    first = json.loads(path.read_text(encoding="utf-8"))

    assert first["run_id"] == "run-1"
    assert first["sessions"][0]["evidence_type"] == "live_api_usage"
    assert "not-to-save" not in path.read_text(encoding="utf-8")
    assert load_api_usage_totals(path)["global_token_limit"] == 64000


def test_ui_appends_usage_sessions_for_the_same_run(tmp_path):
    config = ModelConfig("https://example.test/v1", "unused", "test-model")
    path = tmp_path / "run" / "api_usage.json"

    save_api_usage_evidence(path, "run-2", OpenAICompatibleClient(config), config, "paused")
    save_api_usage_evidence(path, "run-2", OpenAICompatibleClient(config), config, "completed")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["sessions"]) == 2
    assert payload["sessions"][-1]["status_at_save"] == "completed"


def test_standard_run_report_preserves_tool_and_acceptance_evidence(tmp_path):
    workspace = tmp_path / "workspaces" / "run-3"
    workspace.mkdir(parents=True)
    report = RunReport(
        goal="create a calculator",
        status="failed",
        results={
            "implementation": AgentResult(
                "implementation",
                "failed",
                failures=["missing artifact"],
                tool_records=[{"tool": "file_editor", "success": True}],
            )
        },
        rounds=1,
        started_at="2026-11-04T00:00:00+00:00",
        finished_at="2026-11-04T00:00:01+00:00",
    )
    path = tmp_path / "runs" / "run-3" / "run_report.json"

    save_standard_run_evidence(path, "run-3", workspace, report)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["run_id"] == "run-3"
    assert payload["status"] == "failed"
    assert payload["results"]["implementation"]["tool_records"][0]["tool"] == "file_editor"
