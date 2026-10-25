from __future__ import annotations

from datetime import timedelta

from .errors import InvalidCredentialsError, TokenNotFoundError, ValidationError
from .models import AuthenticatedUser, LoginResult, User
from .passwords import PasswordHasher
from .repository import InMemoryUserRepository
from .tokens import TokenStore


class AuthService:
    def __init__(
        self,
        users: InMemoryUserRepository | None = None,
        passwords: PasswordHasher | None = None,
        tokens: TokenStore | None = None,
    ) -> None:
        self.users = users or InMemoryUserRepository()
        self.passwords = passwords or PasswordHasher()
        self.tokens = tokens or TokenStore(ttl=timedelta(hours=1))

    def register(self, username: str, password: str) -> AuthenticatedUser:
        username = self._validate_username(username)
        self._validate_password(password)
        user = self.users.create(username, self.passwords.hash_password(password))
        return self._public_user(user)

    def login(self, username: str, password: str) -> LoginResult:
        username = self._validate_username(username)
        if not password:
            raise InvalidCredentialsError("invalid username or password")

        user = self.users.find_by_username(username)
        if user is None or not self.passwords.verify(password, user.password_hash):
            raise InvalidCredentialsError("invalid username or password")

        session = self.tokens.create(user.id)
        return LoginResult(
            user=self._public_user(user),
            access_token=session.token,
            expires_at=session.expires_at,
        )

    def authenticate(self, access_token: str) -> AuthenticatedUser:
        if not access_token or not access_token.strip():
            raise TokenNotFoundError("access token was not found")
        session = self.tokens.get(access_token.strip())
        user = self.users.find_by_id(session.user_id)
        if user is None:
            raise TokenNotFoundError("access token was not found")
        return self._public_user(user)

    def logout(self, access_token: str) -> None:
        self.tokens.revoke(access_token)

    @staticmethod
    def _public_user(user: User) -> AuthenticatedUser:
        return AuthenticatedUser(id=user.id, username=user.username)

    @staticmethod
    def _validate_username(username: str) -> str:
        if not isinstance(username, str):
            raise ValidationError("username must be a string")
        normalized = username.strip().lower()
        if len(normalized) < 3:
            raise ValidationError("username must contain at least 3 characters")
        if not all(char.isalnum() or char in {"_", "-", "."} for char in normalized):
            raise ValidationError("username may only contain letters, numbers, dots, underscores, and hyphens")
        return normalized

    @staticmethod
    def _validate_password(password: str) -> None:
        if not isinstance(password, str):
            raise ValidationError("password must be a string")
        if len(password) < 8:
            raise ValidationError("password must contain at least 8 characters")
