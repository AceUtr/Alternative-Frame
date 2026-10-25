from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from .errors import DuplicateUserError
from .models import User


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users_by_name: dict[str, User] = {}
        self._users_by_id: dict[str, User] = {}

    def create(self, username: str, password_hash: str) -> User:
        normalized = self.normalize_username(username)
        if normalized in self._users_by_name:
            raise DuplicateUserError("username is already registered")

        user = User(
            id=str(uuid4()),
            username=normalized,
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc),
        )
        self._users_by_name[normalized] = user
        self._users_by_id[user.id] = user
        return replace(user)

    def find_by_username(self, username: str) -> User | None:
        user = self._users_by_name.get(self.normalize_username(username))
        return replace(user) if user else None

    def find_by_id(self, user_id: str) -> User | None:
        user = self._users_by_id.get(user_id)
        return replace(user) if user else None

    @staticmethod
    def normalize_username(username: str) -> str:
        return username.strip().lower()
