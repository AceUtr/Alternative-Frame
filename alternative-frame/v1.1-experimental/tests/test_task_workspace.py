import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.task_workspace import task_workspace


def test_default_user_task_workspace_is_unique_and_outside_repository_root(tmp_path):
    first = task_workspace(tmp_path, "run-1")
    second = task_workspace(tmp_path, "run-2")

    assert first == (tmp_path / "runs" / "user_tasks" / "workspaces" / "run-1").resolve()
    assert first != second
    assert first != tmp_path.resolve()
    assert first.name == "run-1"


def test_selected_project_workspace_is_used_only_when_explicit(tmp_path):
    selected = tmp_path / "existing-project"

    assert task_workspace(tmp_path, "run-1", selected=selected) == selected.resolve()


def test_long_horizon_keeps_its_separate_run_workspace(tmp_path):
    workspace = task_workspace(tmp_path, "run-1", long_horizon=True)

    assert workspace == (tmp_path / "runs" / "long_horizon" / "workspaces" / "run-1").resolve()
