import {
  createHmac,
  randomBytes,
  randomUUID,
  scryptSync,
  timingSafeEqual,
} from "node:crypto";

export interface User {
  id: string;
  email: string;
  createdAt: string;
}

export interface StoredUser extends User {
  passwordHash: string;
}

export interface UserRepository {
  findByEmail(normalizedEmail: string): StoredUser | undefined;
  findById(id: string): StoredUser | undefined;
  create(user: StoredUser): void;
}

export class InMemoryUserRepository implements UserRepository {
  readonly #byEmail = new Map<string, StoredUser>();
  readonly #byId = new Map<string, StoredUser>();

  findByEmail(email: string): StoredUser | undefined {
    return this.#byEmail.get(email);
  }

  findById(id: string): StoredUser | undefined {
    return this.#byId.get(id);
  }

  create(user: StoredUser): void {
    if (this.#byEmail.has(user.email)) throw new AuthError("EMAIL_ALREADY_REGISTERED", "该邮箱已注册", 409);
    this.#byEmail.set(user.email, user);
    this.#byId.set(user.id, user);
  }
}

export type AuthErrorCode =
  | "INVALID_EMAIL"
  | "WEAK_PASSWORD"
  | "EMAIL_ALREADY_REGISTERED"
  | "INVALID_CREDENTIALS"
  | "AUTHENTICATION_REQUIRED"
  | "INVALID_TOKEN"
  | "TOKEN_EXPIRED";

export class AuthError extends Error {
  constructor(
    public readonly code: AuthErrorCode,
    message: string,
    public readonly status: 400 | 401 | 409,
  ) {
    super(message);
    this.name = "AuthError";
  }
}

export interface AuthServiceOptions {
  tokenSecret: string;
  tokenTtlSeconds?: number;
  minimumPasswordLength?: number;
  now?: () => Date;
}

export interface LoginResult {
  accessToken: string;
  tokenType: "Bearer";
  expiresIn: number;
  user: User;
}

interface TokenClaims {
  sub: string;
  email: string;
  iat: number;
  exp: number;
  jti: string;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/u;
const HASH_KEY_LENGTH = 64;
const DUMMY_PASSWORD_HASH = hashPassword("invalid-credential-placeholder", Buffer.alloc(16));

export class AuthService {
  readonly #ttl: number;
  readonly #minimumPasswordLength: number;
  readonly #now: () => Date;
  readonly #secret: string;

  constructor(
    private readonly users: UserRepository,
    options: AuthServiceOptions,
  ) {
    if (typeof options.tokenSecret !== "string" || Buffer.byteLength(options.tokenSecret) < 32) {
      throw new Error("tokenSecret 必须至少为 32 字节");
    }
    this.#secret = options.tokenSecret;
    this.#ttl = options.tokenTtlSeconds ?? 3600;
    this.#minimumPasswordLength = options.minimumPasswordLength ?? 8;
    this.#now = options.now ?? (() => new Date());
    if (!Number.isInteger(this.#ttl) || this.#ttl <= 0) throw new Error("tokenTtlSeconds 必须为正整数");
    if (!Number.isInteger(this.#minimumPasswordLength) || this.#minimumPasswordLength <= 0) {
      throw new Error("minimumPasswordLength 必须为正整数");
    }
  }

  register(input: { email: string; password: string }): User {
    const email = normalizeAndValidateEmail(input?.email);
    this.#validatePassword(input?.password);
    if (this.users.findByEmail(email)) throw new AuthError("EMAIL_ALREADY_REGISTERED", "该邮箱已注册", 409);

    const stored: StoredUser = {
      id: randomUUID(),
      email,
      passwordHash: hashPassword(input.password),
      createdAt: this.#now().toISOString(),
    };
    this.users.create(stored);
    return publicUser(stored);
  }

  login(input: { email: string; password: string }): LoginResult {
    const email = normalizeEmail(input?.email);
    const user = email ? this.users.findByEmail(email) : undefined;
    // Always perform one costly comparison so unknown-email and wrong-password paths are less distinguishable.
    const valid = typeof input?.password === "string" && verifyPassword(input.password, user?.passwordHash ?? DUMMY_PASSWORD_HASH);
    if (!user || !valid) throw new AuthError("INVALID_CREDENTIALS", "邮箱或密码错误", 401);

    const issuedAt = Math.floor(this.#now().getTime() / 1000);
    const claims: TokenClaims = {
      sub: user.id,
      email: user.email,
      iat: issuedAt,
      exp: issuedAt + this.#ttl,
      jti: randomUUID(),
    };
    return {
      accessToken: this.#sign(claims),
      tokenType: "Bearer",
      expiresIn: this.#ttl,
      user: publicUser(user),
    };
  }

  authenticate(authorization: string | undefined): User {
    const match = /^Bearer\s+([^\s]+)$/iu.exec(authorization ?? "");
    if (!match) throw new AuthError("AUTHENTICATION_REQUIRED", "需要 Bearer 访问令牌", 401);
    const claims = this.#verify(match[1]);
    const user = this.users.findById(claims.sub);
    if (!user || user.email !== claims.email) throw new AuthError("INVALID_TOKEN", "访问令牌无效", 401);
    return publicUser(user);
  }

  #validatePassword(password: string): void {
    if (typeof password !== "string" || password.length < this.#minimumPasswordLength) {
      throw new AuthError("WEAK_PASSWORD", `密码长度不能少于 ${this.#minimumPasswordLength} 个字符`, 400);
    }
  }

  #sign(claims: TokenClaims): string {
    const header = encodeJson({ alg: "HS256", typ: "JWT" });
    const payload = encodeJson(claims);
    return `${header}.${payload}.${signature(`${header}.${payload}`, this.#secret)}`;
  }

  #verify(token: string): TokenClaims {
    const parts = token.split(".");
    if (parts.length !== 3) throw new AuthError("INVALID_TOKEN", "访问令牌无效", 401);
    const [header, payload, suppliedSignature] = parts;
    const expectedSignature = signature(`${header}.${payload}`, this.#secret);
    const supplied = Buffer.from(suppliedSignature, "utf8");
    const expected = Buffer.from(expectedSignature, "utf8");
    if (supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) {
      throw new AuthError("INVALID_TOKEN", "访问令牌无效", 401);
    }

    try {
      const parsedHeader = JSON.parse(Buffer.from(header, "base64url").toString("utf8")) as Record<string, unknown>;
      const claims = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as Partial<TokenClaims>;
      if (parsedHeader.alg !== "HS256" || parsedHeader.typ !== "JWT" ||
          typeof claims.sub !== "string" || typeof claims.email !== "string" ||
          typeof claims.iat !== "number" || typeof claims.exp !== "number" || typeof claims.jti !== "string") {
        throw new Error("invalid claims");
      }
      if (claims.exp <= Math.floor(this.#now().getTime() / 1000)) {
        throw new AuthError("TOKEN_EXPIRED", "访问令牌已过期", 401);
      }
      return claims as TokenClaims;
    } catch (error) {
      if (error instanceof AuthError) throw error;
      throw new AuthError("INVALID_TOKEN", "访问令牌无效", 401);
    }
  }
}

function normalizeEmail(value: unknown): string {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function normalizeAndValidateEmail(value: unknown): string {
  const email = normalizeEmail(value);
  if (!EMAIL_PATTERN.test(email)) throw new AuthError("INVALID_EMAIL", "邮箱格式无效", 400);
  return email;
}

function hashPassword(password: string, suppliedSalt = randomBytes(16)): string {
  const salt = suppliedSalt.toString("base64url");
  const hash = scryptSync(password, suppliedSalt, HASH_KEY_LENGTH).toString("base64url");
  return `scrypt$${salt}$${hash}`;
}

function verifyPassword(password: string, encoded: string): boolean {
  const [algorithm, salt, expected] = encoded.split("$");
  if (algorithm !== "scrypt" || !salt || !expected) return false;
  const actual = scryptSync(password, Buffer.from(salt, "base64url"), HASH_KEY_LENGTH);
  const expectedBuffer = Buffer.from(expected, "base64url");
  return actual.length === expectedBuffer.length && timingSafeEqual(actual, expectedBuffer);
}

function encodeJson(value: unknown): string {
  return Buffer.from(JSON.stringify(value), "utf8").toString("base64url");
}

function signature(content: string, secret: string): string {
  return createHmac("sha256", secret).update(content).digest("base64url");
}

function publicUser(user: StoredUser): User {
  return { id: user.id, email: user.email, createdAt: user.createdAt };
}
