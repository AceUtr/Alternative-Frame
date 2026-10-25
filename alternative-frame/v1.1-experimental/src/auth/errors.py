class AuthError(Exception):
    """Base exception for authentication failures."""


class ValidationError(AuthError):
    """Raised when registration or login input is malformed."""


class DuplicateUserError(AuthError):
    """Raised when a username is already registered."""


class InvalidCredentialsError(AuthError):
    """Raised when login credentials do not match a user."""


class TokenNotFoundError(AuthError):
    """Raised when an access token is unknown or already revoked."""


class TokenExpiredError(AuthError):
    """Raised when an access token exists but is no longer valid."""
