import time

import pytest

from core.experimental.adapters import JsonlEventLog
from core.experimental.cost_guard import BudgetExceeded, CostBudget, CostGuard, Usage
from core.experimental.coordination import BoundedMessageBus, TaskQueue
from core.experimental.memory import HybridMemory


def test_cost_guard_reserves_and_reconciles_actual_usage():
    guard = CostGuard(CostBudget(max_requests=2, max_tokens=10, max_cost_usd=1, input_usd_per_million=10, output_usd_per_million=20))
    reservation = guard.reserve(Usage(2, 2))
    guard.settle(reservation, Usage(3, 2))
    assert guard.snapshot()["total_tokens"] == 5
    with pytest.raises(BudgetExceeded, match="token"):
        guard.reserve(Usage(6, 0))


def test_cost_guard_does_not_allow_two_pending_calls_to_overcommit():
    guard = CostGuard(CostBudget(max_tokens=5))
    guard.reserve(Usage(3, 0))
    with pytest.raises(BudgetExceeded):
        guard.reserve(Usage(3, 0))


def test_queue_claim_ack_and_expired_lease_recovery(tmp_path):
    queue = TaskQueue(tmp_path / "tasks.sqlite3")
    task_id = queue.enqueue({"goal": "inspect"})
    claimed = queue.claim("agent-a", lease_seconds=0.01)
    assert claimed["id"] == task_id
    with pytest.raises(ValueError):
        queue.ack(task_id, "agent-b", {"ok": True})
    time.sleep(0.03)
    reclaimed = queue.claim("agent-b", lease_seconds=1)
    assert reclaimed["id"] == task_id
    queue.ack(task_id, "agent-b", {"ok": True})
    assert queue.get(task_id)["status"] == "done"


def test_message_bus_enforces_topology_and_ttl():
    bus = BoundedMessageBus({"main": {"worker"}, "worker": {"main"}}, max_ttl_seconds=5)
    message = bus.send("main", "worker", {"kind": "proposal"})
    assert bus.receive("worker")[0].id == message.id
    with pytest.raises(ValueError):
        bus.send("main", "unknown", {})


def test_hybrid_memory_is_namespaced_and_searchable():
    memory = HybridMemory()
    memory.add("strategy", "retry transient API timeout with fallback model")
    memory.add("execution", "the test runner reported a missing artifact")
    results = memory.search("strategy", "fallback API timeout")
    assert len(results) == 1
    assert "fallback" in results[0]["content"]


def test_hybrid_memory_can_match_chinese_queries():
    memory = HybridMemory()
    memory.add("strategy", "发生网络超时后切换备用模型")
    assert memory.search("strategy", "网络超时备用模型")


def test_event_log_is_jsonl(tmp_path):
    path = tmp_path / "events.jsonl"
    JsonlEventLog(path).emit("task_claimed", {"task_id": "x"})
    assert '"event": "task_claimed"' in path.read_text(encoding="utf-8")
