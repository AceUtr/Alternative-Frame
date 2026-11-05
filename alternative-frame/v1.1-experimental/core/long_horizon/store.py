from __future__ import annotations

import json
import hashlib
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List

from .state import LongHorizonState


class LongHorizonStore:
    """Persist resumable state and append-only events under one run directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._event_lock = threading.Lock()

    @classmethod
    def _safe_event_value(cls, value: Any, depth: int = 0) -> Any:
        if depth > 24:
            return "<truncated>"
        if isinstance(value, dict):
            safe = {}
            for key, item in value.items():
                if re.search(r"(?i)(api[_ -]?key|authorization|password|secret|access[_ -]?token)", str(key)):
                    safe[str(key)] = "<redacted>"
                else:
                    safe[str(key)] = cls._safe_event_value(item, depth + 1)
            return safe
        if isinstance(value, (list, tuple)):
            return [cls._safe_event_value(item, depth + 1) for item in value[:1000]]
        if isinstance(value, str):
            redacted = re.sub(r"(?i)(api[_ -]?key|authorization|bearer|token|password|secret)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", value)
            redacted = re.sub(r"sk-[A-Za-z0-9_-]{16,}", "<redacted>", redacted)
            return redacted[:4000]
        return value

    @staticmethod
    def task_fingerprint(task) -> str:
        from dataclasses import asdict
        data = asdict(task)
        for key in ("runtime_attempt", "retry_feedback", "local_recovery_feedback", "prior_artifacts", "prior_tool_results"):
            data["metadata"].pop(key, None)
        return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    @staticmethod
    def artifact_hashes(result, workspace) -> Dict[str, str]:
        root = Path(workspace).resolve()
        hashes = {}
        for name in result.artifacts:
            if str(name).startswith("artifact://"):
                continue
            target = (root / name).resolve()
            if target != root and root not in target.parents:
                continue
            files = [target] if target.is_file() else sorted(target.rglob("*")) if target.is_dir() else []
            for path in files:
                if path.is_file() and root in path.resolve().parents:
                    hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

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
        record = {"time": utc_now(), "event": event, "payload": self._safe_event_value(payload or {})}
        with self._event_lock:
            event_path = run_dir / "events.jsonl"
            if event_path.is_file():
                with event_path.open("rb+") as recovery:
                    recovery.seek(0, os.SEEK_END)
                    size = recovery.tell()
                    if size:
                        recovery.seek(-1, os.SEEK_END)
                        if recovery.read(1) != b"\n":
                            recovery.seek(0)
                            prior = recovery.read()
                            recovery.truncate(prior.rfind(b"\n") + 1)
            with (run_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

    def successful_results(self, run_id: str, phase: int, plan, workspace: str | Path) -> Dict[str, Any]:
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.is_file():
            return {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return {}
        from ..acceptance import AcceptanceEvaluator
        from ..models import AgentResult
        found: Dict[str, Any] = {}
        task_ids = set(plan.task_map())
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict) or record.get("event") not in {"task_finished", "task_started"}:
                continue
            payload = record.get("payload") or {}
            if not isinstance(payload, dict) or payload.get("phase") != phase:
                continue
            task_id, data = payload.get("task_id"), payload.get("result")
            if record.get("event") == "task_started":
                found.pop(task_id, None)
                continue
            if not task_id or (task_ids is not None and task_id not in task_ids) or not isinstance(data, dict):
                continue
            try:
                result = AgentResult(**data)
            except (TypeError, ValueError):
                continue
            task = plan.task_map()[task_id]
            found.pop(task_id, None)
            hashes = payload.get("artifact_hashes")
            # Old logs without a task fingerprint are evidence only; rerun them.
            if payload.get("task_fingerprint") != self.task_fingerprint(task) or not isinstance(hashes, dict):
                continue
            if any(check.get("check_type") == "command" for check in task.metadata.get("checks", [])):
                continue  # verification commands must run again on resume
            try:
                artifacts_valid = self.artifact_hashes(result, workspace) == hashes
                outputs_valid = all((Path(workspace) / name).exists() for name in task.metadata.get("expected_outputs", []))
            except OSError:
                continue
            if result.subtask_id == task_id and result.status == "success" and artifacts_valid and outputs_valid and AcceptanceEvaluator(workspace).evaluate(task, result).passed:
                found[task_id] = result
        # A cached downstream result is unsafe when any predecessor must rerun.
        changed = True
        while changed:
            changed = False
            for task_id in list(found):
                if any(dep not in found for dep in plan.task_map()[task_id].depends_on):
                    found.pop(task_id)
                    changed = True
        return found
