# Auth Module

This package implements local user registration, login, token authentication, and logout.

- `AuthService.register(username, password)` creates a user with a PBKDF2-SHA256 password hash.
- `AuthService.login(username, password)` verifies credentials and returns an access token.
- `AuthService.authenticate(access_token)` resolves a valid token to the authenticated user.
- `AuthService.logout(access_token)` revokes a token.

The default repository and token store are in-memory. They are intentionally small and can be replaced by persistent adapters later without changing the service API.
