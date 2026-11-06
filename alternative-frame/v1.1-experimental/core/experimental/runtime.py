"""Opt-in integrations; the existing DAG, acceptance and budget stay authoritative."""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from uuid import uuid4
from datetime import datetime, timezone
import subprocess

from .memory import HybridMemory
from .coordination import BoundedMessageBus, TaskQueue
from .cost_guard import CostBudget, CostGuard, Usage
from ..long_horizon.store import LongHorizonStore


def record_execution_metadata(run_dir, workspace, goal, options, config, mode):
    """Capture actual source contents, not just a possibly dirty HEAD. No secrets."""
    root = Path(__file__).resolve().parents[2]
    hashes = {str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root / "core").rglob("*.py"))}
    hashes["ui.py"] = hashlib.sha256((root / "ui.py").read_bytes()).hexdigest()
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no", "--", "."], cwd=root, text=True, stderr=subprocess.DEVNULL).strip())
    except (OSError, subprocess.CalledProcessError):
        head, dirty = None, None
    metadata = {"recorded_at": datetime.now(timezone.utc).isoformat(), "goal_sha256": hashlib.sha256(goal.encode()).hexdigest(), "mode": mode, "workspace": str(Path(workspace).resolve()), "head": head, "dirty_tracked_worktree": dirty, "source_sha256": hashes, "plugin_options": asdict(options), "model": config.model, "temperature": config.temperature, "limits": {"output_tokens": config.max_tokens, "global_tokens": config.global_token_limit, "calls": config.max_model_calls, "seconds": config.max_runtime_seconds, "phases": config.long_horizon_max_phases, "tasks": config.long_horizon_max_tasks}}
    target = Path(run_dir) / "execution_metadata.json"
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"sessions": []}
    previous["sessions"].append(metadata)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


@dataclass(frozen=True)
class PluginOptions:
    bm25: bool = False
    messages: bool = False
    task_queue: bool = False
    usage_audit: bool = False

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise ValueError("invalid plugin configuration")
        if any(type(item) is not bool for item in value.values()):
            raise ValueError("plugin selections must be booleans")
        return cls(**value)

    @property
    def enabled(self):
        return any(asdict(self).values())


class RuntimePlugins:
    """One run, bounded context and durable provenance; no global memory import."""

    def __init__(self, options, run_dir, workspace, goal, on_event=None):
        self.options = options
        self.root = Path(run_dir) / "plugins"
        self.root.mkdir(parents=True, exist_ok=True)
        self.workspace = Path(workspace).resolve()
        self.goal_hash = hashlib.sha256(goal.encode("utf-8")).hexdigest()
        self.lock = RLock()
        self.on_event = on_event
        self._process_lock = None
        self.store = LongHorizonStore(self.root)
        self.memory = HybridMemory() if options.bm25 else None
        self.queue = TaskQueue(self.root / "tasks.sqlite3") if options.task_queue else None
        self.audit = CostGuard(CostBudget()) if options.usage_audit else None
        self._audit_calls = 0
        self._audit_tokens = 0
        target = self.root / "config.json"
        config = {"schema_version": 1, "goal_sha256": self.goal_hash, "options": asdict(options)}
        if target.exists():
            if json.loads(target.read_text(encoding="utf-8")) != config:
                raise ValueError("plugin configuration/goal differs from saved run; start a new run for comparison")
        if options.enabled:
            self._process_lock = (self.root / "runtime.lock").open("a+b")
            self._process_lock.seek(0)
            if os.fstat(self._process_lock.fileno()).st_size == 0:
                self._process_lock.write(b"0")
                self._process_lock.flush()
            self._process_lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self._process_lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._process_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                self._process_lock.close()
                self._process_lock = None
                raise RuntimeError("another plugin runtime already owns this run; do not resume it in two windows") from exc
        if not target.exists():
            temp = target.with_suffix(".tmp")
            temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, target)
        if self.queue:
            # Exclusive run ownership above makes old claimed rows abandoned.
            with self.queue._connect() as db:
                count = db.execute("UPDATE tasks SET status='pending', owner=NULL, lease_until=NULL WHERE status='claimed'").rowcount
            self.emit("plugin_abandoned_leases_recovered", {"count": count})
        if self.memory:
            path = self.store.run_dir("memory") / "events.jsonl"
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)["payload"]
                        self.memory.add(self.goal_hash, row["content"], row["metadata"], row["id"])
                    except (ValueError, KeyError, TypeError):
                        continue
        self.emit("plugins_configured", {"options": asdict(options), "goal_sha256": self.goal_hash})

    def close(self):
        handle = getattr(self, "_process_lock", None)
        if handle is not None:
            handle.close()
            self._process_lock = None

    def __del__(self):
        self.close()

    def emit(self, event, payload):
        safe = LongHorizonStore._safe_event_value(payload)
        self.store.append_event("audit", event, safe)
        if self.on_event:
            self.on_event(event, safe)

    def _valid_memory(self, row):
        hashes = row["metadata"].get("artifact_hashes", {})
        for rel, digest in hashes.items():
            path = (self.workspace / rel).resolve()
            if self.workspace not in path.parents or not path.is_file():
                return False
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    return False
            except OSError:
                return False
        return True

    def prepare_task(self, task, current):
        task = deepcopy(task)
        context = {"policy": "Historical references only. Current task and contract override these notes. Recheck claims and files; prior success is not current acceptance."}
        with self.lock:
            if self.memory:
                candidates = self.memory.search(self.goal_hash, task.description, limit=12)
                hits = []
                for row in candidates:
                    if not self._valid_memory(row):
                        continue
                    item = {"id": row["id"], "content": row["content"][:900], "source": row["metadata"]}
                    if len(json.dumps(hits + [item], ensure_ascii=False)) > 4500:
                        break
                    hits.append(item)
                    if len(hits) == 3:
                        break
                context["retrieved_memory"] = hits
                self.emit("plugin_memory_retrieved", {"task_id": task.id, "query": task.description[:500], "injected": hits})
            if self.options.messages:
                # Scoped bus per dispatch: no stale mailbox or concurrent recipient collision.
                recipient = "agent:" + task.role
                bus = BoundedMessageBus({"coordinator": {recipient}, recipient: {"coordinator"}})
                for dep in task.depends_on[:8]:
                    if dep in current:
                        result = current[dep]
                        bus.send("coordinator", recipient, {"task_id": dep, "status": result.status, "summary": result.summary[:350], "artifacts": [str(a)[:180] for a in result.artifacts[:5]]})
                delivered = []
                for message in bus.receive(recipient):
                    if len(json.dumps(delivered + [message.payload], ensure_ascii=False)) > 4500:
                        break
                    delivered.append(message.payload)
                context["dependency_messages"] = delivered
                self.emit("plugin_messages_delivered", {"task_id": task.id, "messages": context["dependency_messages"]})
        task.metadata["runtime_plugin_context"] = LongHorizonStore._safe_event_value(context)
        return task

    def run_task(self, task, current, execute):
        ticket = None
        if self.queue:
            fingerprint = LongHorizonStore.task_fingerprint(task)
            dependency_versions = {dep: {"summary": current[dep].summary, "artifacts": LongHorizonStore.artifact_hashes(current[dep], self.workspace)} for dep in task.depends_on if dep in current}
            ticket = hashlib.sha256(json.dumps({"fingerprint": fingerprint, "dependencies": dependency_versions}, sort_keys=True).encode()).hexdigest()
            existing = self.queue.get(ticket)
            if existing is None:
                self.queue.enqueue({"task_id": task.id, "task_fingerprint": fingerprint, "goal_sha256": self.goal_hash}, task_id=ticket)
            elif existing["status"] == "done":
                # Never bypass the existing artifact/contract resume validation.
                with self.queue._connect() as db:
                    db.execute("UPDATE tasks SET status='pending', owner=NULL, result=NULL WHERE id=? AND status='done'", (ticket,))
            if self.queue.claim_id(ticket, task.role) is None:
                raise RuntimeError("plugin task lease unavailable")
            self.emit("plugin_task_claimed", {"task_id": task.id, "ticket": ticket})
        try:
            original, result = execute(task, current)
            if self.memory:
                hashes = LongHorizonStore.artifact_hashes(result, self.workspace)
                record_id = uuid4().hex
                content = LongHorizonStore._safe_event_value(f"Task: {task.description[:500]}\nStatus: {result.status}\nSummary: {result.summary[:1400]}\nFailures: {result.failures[:3]}")
                metadata = {"task_id": task.id, "role": task.role, "status": result.status, "artifact_hashes": hashes, "acceptance_evidence": result.evidence[-4:]}
                row = LongHorizonStore._safe_event_value({"id": record_id, "content": content, "metadata": metadata})
                with self.lock:
                    self.memory.add(self.goal_hash, row["content"], row["metadata"], record_id)
                    self.store.append_event("memory", "record", row)
                self.emit("plugin_memory_written", {"task_id": task.id, "record_id": record_id, "status": result.status})
            if ticket:
                self.queue.ack(ticket, task.role, {"status": result.status, "artifacts": result.artifacts})
                self.emit("plugin_task_acknowledged", {"task_id": task.id, "ticket": ticket, "result_status": result.status})
            return original, result
        except BaseException:
            if ticket:
                current_ticket = self.queue.get(ticket)
                if current_ticket and current_ticket["status"] == "claimed":
                    self.queue.release(ticket, task.role)
            raise

    def observe_usage(self, snapshot):
        if not self.audit:
            return
        calls = int(snapshot.get("provider_usage_calls", 0)) + int(snapshot.get("estimated_usage_calls", 0))
        tokens = int(snapshot.get("total_tokens", 0))
        with self.lock:
            if calls == self._audit_calls and tokens == self._audit_tokens:
                return
            if calls < self._audit_calls or tokens < self._audit_tokens:
                raise ValueError("cumulative usage decreased")
            delta_calls, delta_tokens = calls - self._audit_calls, tokens - self._audit_tokens
            for i in range(max(delta_calls, 1)):
                usage = Usage(input_tokens=delta_tokens if i == 0 else 0)
                reservation = self.audit.reserve(usage)
                self.audit.settle(reservation, usage)
            self._audit_calls, self._audit_tokens = calls, tokens
            # CostGuard receives unclassified total tokens, not a real input/output split.
            self.emit("plugin_usage_audited", {"settled_calls": calls, "total_tokens": tokens, "audit_tokens": self.audit.snapshot()["total_tokens"], "cost_usd": None, "cost_status": "unknown", "token_split": "unknown", "enforcement": "existing ModelCallBudget"})
