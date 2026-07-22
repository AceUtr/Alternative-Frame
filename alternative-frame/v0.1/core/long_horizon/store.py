from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .state import LongHorizonState


class LongHorizonStore:
    """Persist resumable state and append-only events under one run directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def run_dir(self, run_id: str) -> Path:
        if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in run_id):
            raise ValueError("run_id may contain only letters, numbers, '-' and '_'")
        path = (self.root / run_id).resolve()
        if self.root not in path.parents:
            raise ValueError("run_id escapes store root")
        return path

    def state_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "state.json"

    def save(self, state: LongHorizonState) -> Path:
        state.touch()
        run_dir = self.run_dir(state.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / "state.json"
        temporary = run_dir / "state.json.tmp"
        temporary.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, target)
        return target

    def load(self, run_id: str) -> LongHorizonState:
        path = self.state_path(run_id)
        if not path.is_file():
            raise FileNotFoundError(f"long-horizon run not found: {run_id}")
        return LongHorizonState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_runs(self) -> List[LongHorizonState]:
        """Return readable runs newest first; ignore partial/corrupt directories."""
        if not self.root.is_dir():
            return []
        runs = []
        for path in self.root.iterdir():
            if not path.is_dir():
                continue
            try:
                runs.append(self.load(path.name))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
        return sorted(runs, key=lambda state: state.updated_at, reverse=True)

    def append_event(self, run_id: str, event: str, payload: Dict[str, Any] | None = None) -> None:
        from ..models import utc_now

        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        record = {"time": utc_now(), "event": event, "payload": payload or {}}
        with (run_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
