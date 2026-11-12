"""Run-scoped, additive acceptance changes consumed at safe phase boundaries."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .acceptance_contract import AcceptanceContract, GoalCriterion
from .contract_validator import ContractValidator


class RuntimeChangeInbox:
    MAX_BYTES = 65536
    REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    FIELDS = {"schema_version", "run_id", "request_id", "base_revision", "description", "add_criteria", "add_constraints"}
    _thread_locks: dict[str, threading.RLock] = {}
    _thread_locks_guard = threading.Lock()

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.pending = self.root / "pending"
        lock_key = str(self.root)
        with self._thread_locks_guard:
            self._thread_lock = self._thread_locks.setdefault(lock_key, threading.RLock())

    @contextmanager
    def lock(self):
        """Serialize inbox updates and completion on this machine across threads/processes."""
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / ".runtime-change.lock"
        with self._thread_lock, lock_path.open("a+b") as stream:
            if os.name == "nt":
                import msvcrt
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"\0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _write_once(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError("an immutable runtime-change record has different content")
            return
        # Write a complete temporary file, then publish without replacing history.
        temporary = path.with_name(path.name + "." + uuid4().hex[:8] + ".tmp")
        try:
            temporary.write_bytes(content)
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError("runtime-change record was concurrently replaced")
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _json_bytes(value: dict) -> bytes:
        return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    def open(self, state) -> None:
        self.pending.mkdir(parents=True, exist_ok=True)
        if not state.acceptance_contract:
            raise ValueError("runtime changes require a persisted acceptance contract")
        self.snapshot_contract(state.contract_revision, state.acceptance_contract)

    def snapshot_contract(self, revision: int, contract: dict) -> Path:
        path = self.root / "contracts" / f"revision-{revision:04d}.json"
        self._write_once(path, self._json_bytes(contract))
        return path

    def pending_paths(self) -> list[Path]:
        return sorted(self.pending.glob("*.json"))[:20]

    def prepare(self, path: Path, state) -> tuple[dict | None, dict]:
        if path.is_symlink() or path.resolve().parent != self.pending.resolve():
            raise ValueError("change request must be a regular file inside the run inbox")
        raw = path.read_bytes()
        if len(raw) > self.MAX_BYTES:
            raise ValueError("change request exceeds the 64 KiB limit")
        request = json.loads(raw.decode("utf-8"))
        if not isinstance(request, dict) or set(request) - self.FIELDS:
            raise ValueError("change request contains unsupported fields")
        if type(request.get("schema_version")) is not int or request.get("schema_version") != 1 or request.get("run_id") != state.run_id:
            raise ValueError("change request schema or run identity does not match")
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not self.REQUEST_ID.fullmatch(request_id):
            raise ValueError("invalid change request ID")
        digest = hashlib.sha256(raw).hexdigest()
        prior = next((item for item in state.runtime_changes if item["request_id"] == request_id), None)
        if prior:
            if prior["request_sha256"] != digest:
                raise ValueError("a previously applied request ID was reused with different content")
            return None, prior
        base_revision = request.get("base_revision")
        if type(base_revision) is not int or base_revision != state.contract_revision:
            raise ValueError("change request base revision does not match the active contract")
        description = request.get("description")
        if not isinstance(description, str) or not description.strip() or len(description) > 4000:
            raise ValueError("change description must contain 1 to 4000 characters")
        additions = request.get("add_criteria")
        constraints = request.get("add_constraints", [])
        if not isinstance(additions, list) or not additions or not all(isinstance(item, dict) for item in additions):
            raise ValueError("change request requires non-empty add_criteria")
        if not isinstance(constraints, list) or len(constraints) > 20 or not all(
            isinstance(item, str) and item.strip() and len(item) <= 1000 for item in constraints
        ):
            raise ValueError("add_constraints must contain at most 20 non-empty strings of 1000 characters or fewer")
        contract = AcceptanceContract.from_dict(state.acceptance_contract)
        contract.criteria.extend(GoalCriterion.from_dict(item) for item in additions)
        contract.constraints.extend(constraints)
        ContractValidator().validate(contract, expected_goal=state.goal)
        revision = state.contract_revision + 1
        snapshot = self.root / "accepted" / (request_id + ".json")
        self._write_once(snapshot, raw)
        contract_path = self.snapshot_contract(revision, contract.to_dict())
        record = {
            "request_id": request_id,
            "request_sha256": digest,
            "base_revision": base_revision,
            "revision": revision,
            "description": description,
            "added_criteria": [item["id"] for item in additions],
            "request_path": str(snapshot),
            "contract_path": str(contract_path),
        }
        return contract.to_dict(), record

    def acknowledge(self, path: Path, digest: str) -> None:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            path.unlink()

    def reject(self, path: Path, reason: str) -> dict:
        raw = path.read_bytes() if path.is_file() and not path.is_symlink() else b""
        digest = hashlib.sha256(raw).hexdigest()
        archive = self.root / "rejected" / (digest + ".json")
        self._write_once(archive, raw)
        if path.is_symlink():
            path.unlink(missing_ok=True)
        else:
            self.acknowledge(path, digest)
        return {"request_sha256": digest, "reason": reason, "rejected_path": str(archive)}


def submit_change(run_dir: str | Path, request: dict) -> Path:
    """Atomically publish an assessor-supplied request; never overwrite one."""
    run_dir = Path(run_dir).resolve()
    inbox = RuntimeChangeInbox(run_dir / "runtime_changes")
    with inbox.lock():
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        if not isinstance(request, dict) or set(request) - RuntimeChangeInbox.FIELDS:
            raise ValueError("change request must be an object with supported fields only")
        if state.get("status") != "running":
            raise ValueError("changes can only be submitted to a currently running task")
        if type(request.get("schema_version")) is not int or request.get("schema_version") != 1:
            raise ValueError("unsupported change request schema")
        if request.get("run_id") != state.get("run_id"):
            raise ValueError("request run_id does not match the target run")
        if type(request.get("base_revision")) is not int or request["base_revision"] != state.get("contract_revision", 1):
            raise ValueError("request base_revision does not match the active contract")
        request_id = request.get("request_id", "")
        if not isinstance(request_id, str) or not RuntimeChangeInbox.REQUEST_ID.fullmatch(request_id):
            raise ValueError("invalid change request ID")
        description = request.get("description")
        additions = request.get("add_criteria")
        constraints = request.get("add_constraints", [])
        if not isinstance(description, str) or not description.strip() or len(description) > 4000:
            raise ValueError("change description must contain 1 to 4000 characters")
        if not isinstance(additions, list) or not additions or not all(isinstance(item, dict) for item in additions):
            raise ValueError("change request requires non-empty add_criteria")
        if not isinstance(constraints, list) or len(constraints) > 20 or not all(
            isinstance(item, str) and item.strip() and len(item) <= 1000 for item in constraints
        ):
            raise ValueError("add_constraints must contain at most 20 non-empty strings of 1000 characters or fewer")
        contract = AcceptanceContract.from_dict(state["acceptance_contract"])
        contract.criteria.extend(GoalCriterion.from_dict(item) for item in additions)
        contract.constraints.extend(constraints)
        ContractValidator().validate(contract, expected_goal=state["goal"])
        target = inbox.pending / (request_id + ".json")
        RuntimeChangeInbox._write_once(target, RuntimeChangeInbox._json_bytes(request))
        return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publish an external additive change to a running task")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        print(submit_change(args.run_dir, request))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"runtime change rejected: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
