from __future__ import annotations

from pathlib import Path


def task_workspace(project_dir: str | Path, run_id: str, selected: str | Path | None = None, long_horizon: bool = False) -> Path:
    """Resolve a task workspace; default runs never inherit repository files."""
    if selected is not None:
        return Path(selected).resolve()
    root = Path(project_dir) / "runs"
    root = root / "long_horizon" if long_horizon else root / "user_tasks"
    return (root / "workspaces" / run_id).resolve()
