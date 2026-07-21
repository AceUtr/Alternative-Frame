import test from "node:test";
import assert from "node:assert/strict";
import { AuthError, AuthService, InMemoryUserRepository } from "../src/auth.ts";

const SECRET = "test-only-secret-that-is-at-least-32-bytes-long";
const baseTime = new Date("2026-01-01T00:00:00.000Z");

function fixture(now = baseTime) {
  let current = now;
  const service = new AuthService(new InMemoryUserRepository(), {
    tokenSecret: SECRET,
    tokenTtlSeconds: 60,
    now: () => current,
  });
  return { service, setNow: (value: Date) => { current = value; } };
}

function expectAuthError(code: string, action: () => unknown): void {
  assert.throws(action, (error: unknown) => {
    assert.ok(error instanceof AuthError);
    assert.equal(error.code, code);
    return true;
  });
}

test("register normalizes email and never exposes a password hash", () => {
  const { service } = fixture();
  const user = service.register({ email: " User@Example.COM ", password: "secure-pass" });
  assert.equal(user.email, "user@example.com");
  assert.equal("passwordHash" in user, false);
  expectAuthError("EMAIL_ALREADY_REGISTERED", () => service.register({ email: "USER@example.com", password: "other-pass" }));
});

test("registration validates email and password", () => {
  const { service } = fixture();
  expectAuthError("INVALID_EMAIL", () => service.register({ email: "not-an-email", password: "secure-pass" }));
  expectAuthError("WEAK_PASSWORD", () => service.register({ email: "user@example.com", password: "short" }));
});

test("login returns a bearer token and generic errors for bad credentials", () => {
  const { service } = fixture();
  const registered = service.register({ email: "user@example.com", password: "secure-pass" });
  const session = service.login({ email: "USER@example.com", password: "secure-pass" });
  assert.equal(session.tokenType, "Bearer");
  assert.equal(session.expiresIn, 60);
  assert.equal(session.user.id, registered.id);
  assert.equal(service.authenticate(`Bearer ${session.accessToken}`).id, registered.id);
  expectAuthError("INVALID_CREDENTIALS", () => service.login({ email: "user@example.com", password: "wrong-pass" }));
  expectAuthError("INVALID_CREDENTIALS", () => service.login({ email: "missing@example.com", password: "wrong-pass" }));
});

test("authentication rejects missing, tampered and expired tokens", () => {
  const { service, setNow } = fixture();
  service.register({ email: "user@example.com", password: "secure-pass" });
  const token = service.login({ email: "user@example.com", password: "secure-pass" }).accessToken;
  expectAuthError("AUTHENTICATION_REQUIRED", () => service.authenticate(undefined));
  expectAuthError("INVALID_TOKEN", () => service.authenticate(`Bearer ${token.slice(0, -1)}x`));
  setNow(new Date(baseTime.getTime() + 60_000));
  expectAuthError("TOKEN_EXPIRED", () => service.authenticate(`Bearer ${token}`));
});

test("service refuses weak signing secrets", () => {
  assert.throws(() => new AuthService(new InMemoryUserRepository(), { tokenSecret: "short" }), /32 字节/u);
});
