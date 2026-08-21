import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).parents[1]))

from ui import (
    DEFAULT_EXECUTION_MODES,
    RESEARCH_EXECUTION_MODE,
    SOFTWARE_EXECUTION_MODE,
    run_software_ui_bridge,
)


def test_offline_domain_modes_are_selectable():
    assert RESEARCH_EXECUTION_MODE in DEFAULT_EXECUTION_MODES
    assert SOFTWARE_EXECUTION_MODE in DEFAULT_EXECUTION_MODES


def test_cancelled_software_contract_never_starts_runner(tmp_path):
    called = []
    events = []

    def forbidden_runner(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("runner must not start after cancellation")

    result = run_software_ui_bridge(
        runs_root=tmp_path / "runs",
        fault_scenario="none",
        confirm_contract=lambda _contract: None,
        event_sink=lambda kind, payload: events.append((kind, payload)),
        runner=forbidden_runner,
    )

    assert result is None
    assert called == []
    assert events == [
        ("run_cancelled", "用户取消了软件验收合同，未启动 Controller 或工具")
    ]


@pytest.mark.parametrize(
    ("scenario", "expected_event"),
    [
        ("none", "run_completed"),
        ("retry-once", "retry_summary"),
        ("local-recovery", "local_recovery_started"),
    ],
)
def test_software_ui_bridge_runs_frozen_scenarios(tmp_path, scenario, expected_event):
    events = []

    result = run_software_ui_bridge(
        runs_root=tmp_path / "runs",
        fault_scenario=scenario,
        confirm_contract=lambda contract: contract,
        event_sink=lambda kind, payload: events.append((kind, payload)),
    )

    assert result["status"] == "completed"
    assert result["phase_count"] >= 1
    assert result["state_path"].is_file()
    assert result["events_path"].is_file()
    assert all(path.is_file() for path in result["artifacts"])
    assert expected_event in [event["event"] for event in result["events"]]
    assert [kind for kind, _ in events][-1] == "software_report"

