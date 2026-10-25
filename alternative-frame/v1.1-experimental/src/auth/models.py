from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    id: str
    username: str
    password_hash: str
    created_at: datetime


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str


@dataclass(frozen=True)
class LoginResult:
    user: AuthenticatedUser
    access_token: str
    expires_at: datetime
