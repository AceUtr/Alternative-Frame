"""Bounded agent messaging and a durable SQLite task queue with leases."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Iterable
from uuid import uuid4


@dataclass(frozen=True)
class AgentMessage:
    id: str
    sender: str
    recipient: str
    payload: dict
    created_at: float
    expires_at: float
    hops: int = 0


class BoundedMessageBus:
    def __init__(self, topology: dict[str, Iterable[str]], max_hops: int = 3, max_ttl_seconds: float = 300):
        self.topology = {agent: set(neighbors) for agent, neighbors in topology.items()}
        self.max_hops = max_hops
        self.max_ttl_seconds = max_ttl_seconds
        self._mailboxes: dict[str, list[AgentMessage]] = {agent: [] for agent in self.topology}
        self._seen: set[tuple[str, str]] = set()
        self._lock = RLock()

    def send(self, sender: str, recipient: str, payload: dict, ttl_seconds: float = 60) -> AgentMessage:
        if sender == recipient or recipient not in self.topology.get(sender, set()):
            raise ValueError("message route is not an allowed direct neighbor")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        now = time.time()
        message = AgentMessage(uuid4().hex, sender, recipient, dict(payload), now,
                               now + min(ttl_seconds, self.max_ttl_seconds))
        with self._lock:
            self._mailboxes.setdefault(recipient, []).append(message)
        return message

    def receive(self, agent: str) -> list[AgentMessage]:
        now = time.time()
        with self._lock:
            messages = self._mailboxes.pop(agent, [])
            self._mailboxes.setdefault(agent, [])
            fresh = []
            for message in messages:
                key = (agent, message.id)
                if message.expires_at > now and message.hops <= self.max_hops and key not in self._seen:
                    self._seen.add(key)
                    fresh.append(message)
            return fresh


class TaskQueue:
    """SQLite-backed queue. Expired leases become claimable on the next claim."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, lease_until REAL, attempts INTEGER NOT NULL DEFAULT 0, result TEXT)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def enqueue(self, payload: dict, task_id: str | None = None) -> str:
        task_id = task_id or uuid4().hex
        with self._connect() as db:
            db.execute("INSERT INTO tasks(id,payload,status) VALUES(?,?, 'pending')", (task_id, json.dumps(payload, ensure_ascii=False)))
        return task_id

    def claim(self, agent: str, lease_seconds: float = 60) -> dict | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            now = time.time()
            row = db.execute("SELECT * FROM tasks WHERE status='pending' OR (status='claimed' AND lease_until <= ?) ORDER BY rowid LIMIT 1", (now,)).fetchone()
            if row is None:
                db.execute("COMMIT")
                return None
            db.execute("UPDATE tasks SET status='claimed', owner=?, lease_until=?, attempts=attempts+1 WHERE id=?", (agent, now + lease_seconds, row['id']))
            db.execute("COMMIT")
            return {"id": row["id"], "payload": json.loads(row["payload"]), "owner": agent, "attempt": row["attempts"] + 1, "lease_until": now + lease_seconds}

    def ack(self, task_id: str, agent: str, result: dict) -> None:
        with self._connect() as db:
            cur = db.execute("UPDATE tasks SET status='done', result=?, lease_until=NULL WHERE id=? AND status='claimed' AND owner=?", (json.dumps(result, ensure_ascii=False), task_id, agent))
            if cur.rowcount != 1:
                raise ValueError("task is not leased to this agent")

    def release(self, task_id: str, agent: str) -> None:
        with self._connect() as db:
            cur = db.execute("UPDATE tasks SET status='pending', owner=NULL, lease_until=NULL WHERE id=? AND status='claimed' AND owner=?", (task_id, agent))
            if cur.rowcount != 1:
                raise ValueError("task is not leased to this agent")

    def get(self, task_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "payload": json.loads(row["payload"]), "status": row["status"], "owner": row["owner"], "attempts": row["attempts"], "result": json.loads(row["result"]) if row["result"] else None}
