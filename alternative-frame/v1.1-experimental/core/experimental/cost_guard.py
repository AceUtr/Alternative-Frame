"""Thread-safe admission and accounting for model calls."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from uuid import uuid4


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class CostBudget:
    max_requests: int | None = None
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    input_usd_per_million: float = 0.0
    output_usd_per_million: float = 0.0


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class Reservation:
    id: str
    estimated: Usage


class CostGuard:
    """Reserve estimated usage before a request and reconcile with provider usage."""

    def __init__(self, budget: CostBudget):
        self.budget = budget
        self._lock = Lock()
        self._requests = 0
        self._usage = Usage()
        self._cost = 0.0
        self._pending: dict[str, Usage] = {}

    def _price(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.budget.input_usd_per_million
            + usage.output_tokens * self.budget.output_usd_per_million
        ) / 1_000_000

    def reserve(self, estimated: Usage) -> Reservation:
        if estimated.input_tokens < 0 or estimated.output_tokens < 0:
            raise ValueError("token estimates must be non-negative")
        with self._lock:
            pending = list(self._pending.values())
            reserved_tokens = sum(item.total_tokens for item in pending)
            reserved_cost = sum(self._price(item) for item in pending)
            if self.budget.max_requests is not None and self._requests + len(pending) >= self.budget.max_requests:
                raise BudgetExceeded("request budget exhausted")
            if self.budget.max_tokens is not None and self._usage.total_tokens + reserved_tokens + estimated.total_tokens > self.budget.max_tokens:
                raise BudgetExceeded("token budget would be exceeded")
            if self.budget.max_cost_usd is not None and self._cost + reserved_cost + self._price(estimated) > self.budget.max_cost_usd:
                raise BudgetExceeded("cost budget would be exceeded")
            reservation = Reservation(uuid4().hex, estimated)
            self._pending[reservation.id] = estimated
            return reservation

    def settle(self, reservation: Reservation, actual: Usage) -> None:
        if actual.input_tokens < 0 or actual.output_tokens < 0:
            raise ValueError("actual token usage must be non-negative")
        with self._lock:
            if self._pending.pop(reservation.id, None) is None:
                raise ValueError("unknown or already settled reservation")
            cost = self._cost + self._price(actual)
            tokens = self._usage.total_tokens + actual.total_tokens
            self._requests += 1
            self._usage = Usage(self._usage.input_tokens + actual.input_tokens, self._usage.output_tokens + actual.output_tokens)
            self._cost = cost
            # The provider has already charged for this call, so record actual
            # usage before reporting that the estimate crossed a hard budget.
            if self.budget.max_tokens is not None and tokens > self.budget.max_tokens:
                raise BudgetExceeded("provider usage exceeded token budget after the call completed")
            if self.budget.max_cost_usd is not None and cost > self.budget.max_cost_usd:
                raise BudgetExceeded("provider usage exceeded cost budget after the call completed")

    def cancel(self, reservation: Reservation) -> None:
        with self._lock:
            if self._pending.pop(reservation.id, None) is None:
                raise ValueError("unknown or already settled reservation")

    def snapshot(self) -> dict[str, int | float]:
        with self._lock:
            return {
                "requests": self._requests,
                "input_tokens": self._usage.input_tokens,
                "output_tokens": self._usage.output_tokens,
                "total_tokens": self._usage.total_tokens,
                "cost_usd": self._cost,
                "pending_requests": len(self._pending),
            }
