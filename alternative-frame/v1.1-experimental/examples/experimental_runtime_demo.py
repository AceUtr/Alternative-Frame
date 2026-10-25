"""Run the opt-in runtime components without an API key or external service."""

from pathlib import Path
from tempfile import TemporaryDirectory

from core.experimental.adapters import JsonlEventLog
from core.experimental.cost_guard import CostBudget, CostGuard, Usage
from core.experimental.coordination import BoundedMessageBus, TaskQueue
from core.experimental.memory import HybridMemory


def main() -> None:
    with TemporaryDirectory(prefix="alternative-frame-experimental-") as temp:
        root = Path(temp)
        events = JsonlEventLog(root / "events.jsonl")

        budget = CostGuard(CostBudget(max_requests=3, max_tokens=1000, max_cost_usd=0.01))
        reservation = budget.reserve(Usage(input_tokens=120, output_tokens=80))
        budget.settle(reservation, Usage(input_tokens=105, output_tokens=64))
        events.emit("model_call_accounted", budget.snapshot())

        queue = TaskQueue(root / "tasks.sqlite3")
        task_id = queue.enqueue({"goal": "review the candidate result"})
        claimed = queue.claim("reviewer")
        queue.ack(task_id, claimed["owner"], {"status": "accepted"})
        events.emit("task_completed", queue.get(task_id))

        bus = BoundedMessageBus({"coordinator": {"reviewer"}, "reviewer": {"coordinator"}})
        bus.send("coordinator", "reviewer", {"kind": "review_request", "task_id": task_id})
        events.emit("message_received", {"messages": [message.id for message in bus.receive("reviewer")]})

        memory = HybridMemory()
        memory.add("strategy", "Use a fallback model after repeated transient gateway errors.")
        memory.add("execution", "The test runner confirmed the expected artifact exists.")
        events.emit("memory_hits", {"hits": memory.search("strategy", "fallback gateway errors")})

        print("Budget:", budget.snapshot())
        print("Completed task:", queue.get(task_id))
        print("Memory hits:", memory.search("strategy", "fallback gateway errors"))
        print("Event log:", root / "events.jsonl")


if __name__ == "__main__":
    main()
