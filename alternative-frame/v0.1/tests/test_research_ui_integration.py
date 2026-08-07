import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from run_research_demo import run_demo
from ui import DEFAULT_EXECUTION_MODES, RESEARCH_EXECUTION_MODE


PROJECT_ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = PROJECT_ROOT / "examples" / "research_task"


def _workspace(tmp_path):
    workspace = tmp_path / "research-ui"
    workspace.mkdir(parents=True)
    for name in (
        "generate_dataset.py",
        "run_baseline.py",
        "run_improved.py",
        "verify_best.py",
    ):
        shutil.copy(FIXTURE_ROOT / name, workspace / name)
    return workspace


def test_research_mode_is_available_in_ui():
    assert RESEARCH_EXECUTION_MODE in DEFAULT_EXECUTION_MODES


def test_research_runner_emits_ui_bridge_events(tmp_path):
    events = []
    report = run_demo(
        _workspace(tmp_path),
        tmp_path / "runs",
        "research-ui-bridge",
        fault_scenario="local-recovery",
        on_event=lambda kind, payload: events.append((kind, payload)),
    )

    kinds = {kind for kind, _ in events}
    long_events = {
        payload["event"]
        for kind, payload in events
        if kind == "long_horizon_event"
    }
    evaluator_events = {
        payload["event"]
        for kind, payload in events
        if kind == "global_evaluator_event"
    }

    assert report.status == "completed"
    assert report.state.phase == 2
    assert {"task_event", "long_horizon_event", "global_evaluator_event"} <= kinds
    assert "local_recovery_started" in long_events
    assert "run_completed" in long_events
    assert "global_hard_gate" in evaluator_events
