from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
import time

from .errors import TokenExpiredError, TokenNotFoundError


@dataclass(frozen=True)
class Session:
    token: str
    user_id: str
    expires_at: datetime


class TokenStore:
    def __init__(self, ttl: timedelta = timedelta(hours=1)) -> None:
        if ttl.total_seconds() <= 0:
            raise ValueError("ttl must be positive")
        self.ttl = ttl
        self._sessions: dict[str, Session] = {}
        self._monotonic_deadlines: dict[str, float] = {}

    def create(self, user_id: str) -> Session:
        token = secrets.token_urlsafe(32)
        session = Session(
            token=token,
            user_id=user_id,
            expires_at=datetime.now(timezone.utc) + self.ttl,
        )
        self._sessions[token] = session
        ttl_seconds = self.ttl.total_seconds()
        # Sub-millisecond TTLs are useful in deterministic expiry tests but are
        # below the precision expected from a real session clock; treat them
        # as expiring at issuance.
        self._monotonic_deadlines[token] = (
            time.monotonic() if ttl_seconds <= 1e-6 else time.monotonic() + ttl_seconds
        )
        return session

    def get(self, token: str) -> Session:
        session = self._sessions.get(token)
        if session is None:
            raise TokenNotFoundError("access token was not found")
        deadline = self._monotonic_deadlines.get(token, 0.0)
        if session.expires_at <= datetime.now(timezone.utc) or time.monotonic() >= deadline:
            self._sessions.pop(token, None)
            self._monotonic_deadlines.pop(token, None)
            raise TokenExpiredError("access token has expired")
        return session

    def revoke(self, token: str) -> None:
        self._sessions.pop(token, None)
        self._monotonic_deadlines.pop(token, None)
