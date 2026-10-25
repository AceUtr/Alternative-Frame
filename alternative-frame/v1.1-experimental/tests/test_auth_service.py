from datetime import timedelta

import pytest

from src.auth import AuthService
from src.auth.errors import DuplicateUserError, InvalidCredentialsError, TokenExpiredError, TokenNotFoundError, ValidationError
from src.auth.tokens import TokenStore


def test_register_normalizes_username_and_hides_password_hash() -> None:
    service = AuthService()

    user = service.register("  Alice.Example  ", "correct horse")

    assert user.username == "alice.example"
    assert user.id
    assert not hasattr(user, "password_hash")


def test_register_rejects_duplicate_usernames_case_insensitively() -> None:
    service = AuthService()
    service.register("Alice", "correct horse")

    with pytest.raises(DuplicateUserError):
        service.register("alice", "another secret")


def test_register_validates_username_and_password() -> None:
    service = AuthService()

    with pytest.raises(ValidationError):
        service.register("ab", "correct horse")
    with pytest.raises(ValidationError):
        service.register("valid-user", "short")
    with pytest.raises(ValidationError):
        service.register("bad user", "correct horse")


def test_login_issues_token_and_authenticate_returns_user() -> None:
    service = AuthService()
    registered = service.register("alice", "correct horse")

    result = service.login("ALICE", "correct horse")
    authenticated = service.authenticate(result.access_token)

    assert result.user == registered
    assert authenticated == registered
    assert result.access_token
    assert result.expires_at.tzinfo is not None


def test_login_rejects_unknown_user_and_wrong_password() -> None:
    service = AuthService()
    service.register("alice", "correct horse")

    with pytest.raises(InvalidCredentialsError):
        service.login("missing", "correct horse")
    with pytest.raises(InvalidCredentialsError):
        service.login("alice", "wrong password")


def test_logout_revokes_token() -> None:
    service = AuthService()
    service.register("alice", "correct horse")
    result = service.login("alice", "correct horse")

    service.logout(result.access_token)

    with pytest.raises(TokenNotFoundError):
        service.authenticate(result.access_token)


def test_expired_token_is_rejected() -> None:
    service = AuthService(tokens=TokenStore(ttl=timedelta(microseconds=1)))
    service.register("alice", "correct horse")
    result = service.login("alice", "correct horse")

    with pytest.raises(TokenExpiredError):
        service.authenticate(result.access_token)
