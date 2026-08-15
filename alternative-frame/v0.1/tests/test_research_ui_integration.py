import shutil
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1]))

from run_research_demo import GOAL
from ui import (
    DEFAULT_EXECUTION_MODES,
    RESEARCH_EXECUTION_MODE,
    run_research_ui_bridge,
)


PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "examples" / "research_task"


def _fixture(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    for name in (
        "generate_dataset.py",
        "run_baseline.py",
        "run_improved.py",
        "verify_best.py",
    ):
        shutil.copy(FIXTURE_ROOT / name, root / name)
    return root


def test_research_mode_is_selectable_and_uses_fixed_goal():
    assert RESEARCH_EXECUTION_MODE in DEFAULT_EXECUTION_MODES
    assert "reproducible baseline" in GOAL


def test_cancelled_research_contract_never_starts_runner(tmp_path):
    events = []
    called = []

    def forbidden_runner(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("runner must not start after cancellation")

    report = run_research_ui_bridge(
        fixture_root=_fixture(tmp_path),
        runs_root=tmp_path / "runs",
        run_id="cancelled",
        fault_scenario="normal",
        confirm_contract=lambda _contract: None,
        event_sink=lambda kind, payload: events.append((kind, payload)),
        runner=forbidden_runner,
    )

    assert report is None
    assert called == []
    assert events == [
        ("run_cancelled", "用户取消了科研验收合同，未启动 Controller 或工具")
    ]


def test_confirmed_research_ui_bridge_emits_two_phase_and_evidence_events(tmp_path):
    events = []
    controllers = []

    report = run_research_ui_bridge(
        fixture_root=_fixture(tmp_path),
        runs_root=tmp_path / "runs",
        run_id="ui-normal",
        fault_scenario="normal",
        confirm_contract=lambda contract: contract,
        event_sink=lambda kind, payload: events.append((kind, payload)),
        controller_sink=controllers.append,
    )

    kinds = [kind for kind, _ in events]
    long_events = [
        payload[0] for kind, payload in events if kind == "long_horizon_event"
    ]
    global_events = [
        payload[0] for kind, payload in events if kind == "global_evaluator_event"
    ]
    task_events = [payload[0] for kind, payload in events if kind == "task_event"]

    assert report.status == "completed"
    assert report.state.phase == 2
    assert len(controllers) == 1
    assert "contract_confirmed" in kinds
    assert "preflight_report" in kinds
    assert "research_report" in kinds
    assert "task_started" in task_events
    assert "task_finished" in task_events
    assert "global_hard_gate" in global_events
    assert "run_completed" in long_events


def test_local_recovery_ui_bridge_emits_recovery_timeline(tmp_path):
    events = []

    report = run_research_ui_bridge(
        fixture_root=_fixture(tmp_path),
        runs_root=tmp_path / "runs",
        run_id="ui-local-recovery",
        fault_scenario="local-recovery",
        confirm_contract=lambda contract: contract,
        event_sink=lambda kind, payload: events.append((kind, payload)),
    )

    long_events = [
        payload[0] for kind, payload in events if kind == "long_horizon_event"
    ]
    final_payload = next(payload for kind, payload in events if kind == "research_report")

    assert report.status == "completed"
    assert report.state.phases[0].local_recovery_cycles == 1
    assert "local_recovery_planned" in long_events
    assert "local_recovery_finished" in long_events
    assert final_payload[1].name == "state.json"
    assert final_payload[2].name == "research_report.md"


def test_task_retry_ui_bridge_emits_retry_event(tmp_path):
    events = []

    report = run_research_ui_bridge(
        fixture_root=_fixture(tmp_path),
        runs_root=tmp_path / "runs",
        run_id="ui-task-retry",
        fault_scenario="task-retry",
        confirm_contract=lambda contract: contract,
        event_sink=lambda kind, payload: events.append((kind, payload)),
    )

    task_events = [payload for kind, payload in events if kind == "task_event"]
    retry = next(payload for payload in task_events if payload[0] == "task_retry_scheduled")

    assert report.status == "completed"
    assert retry[1] == "run_baseline"
    assert retry[2].attempts == 1
