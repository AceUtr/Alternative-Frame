from __future__ import annotations

import hashlib
import hmac
import secrets


class PasswordHasher:
    def __init__(self, iterations: int = 120_000) -> None:
        if iterations < 1:
            raise ValueError("iterations must be positive")
        self.iterations = iterations

    def hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = self._derive(password, salt)
        return f"pbkdf2_sha256${self.iterations}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, encoded_hash: str) -> bool:
        try:
            algorithm, iterations, salt_hex, digest_hex = encoded_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = self._derive(password, salt, int(iterations))
            return hmac.compare_digest(actual, expected)
        except (TypeError, ValueError):
            return False

    def _derive(self, password: str, salt: bytes, iterations: int | None = None) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations or self.iterations,
        )
