# EP-05 Knowledge Transfer — Authentication and RBAC Foundation

## Overview

EP-05 implements stateful session management, JWT access tokens, Argon2id password hashing, email verification, password reset, RBAC permission model, and FastAPI authorization dependencies.

---

## Architecture

### Four-layer flow

```
HTTP Request
  → FastAPI router (app/api/v1/auth.py)
    → AuthService (app/auth/service.py)
      → Repositories (session, user, verification_token, password_reset_token)
        → PostgreSQL
```

### Token model — two token types

| Token | Format | Storage | Lifespan |
|-------|--------|---------|----------|
| Access | Signed HS256 JWT | Stateless (none) | 30 min (configurable) |
| Refresh | Opaque `secrets.token_urlsafe(32)` | SHA-256 hash in `sessions` table | 30 days (configurable) |

The access token contains: `sub` (user_id UUID), `jti` (session_id UUID), `email`, `iat`, `exp`, `type: "access"`.

---

## Key Decisions

### Why Argon2id and not bcrypt / scrypt?

Argon2id is the OWASP-recommended algorithm. It is memory-hard (resistant to GPU attacks) and combines data-dependent and data-independent memory access patterns (PHC winner). bcrypt has a 72-byte password limit and lacks memory hardness.

### Why opaque refresh tokens and not JWT refresh tokens?

Opaque tokens stored as SHA-256 hashes enable:
1. **Immediate revocation** — update one row in `sessions`, no need to wait for expiry.
2. **Rotation detection** — refresh token rotation replaces the hash atomically; a replayed old token gets a DB miss.
3. **Admin visibility** — active sessions are enumerable per user.

### Why HS256 and not RS256?

For a single-service deployment with a shared secret, HS256 is simpler and equally secure. RS256 is needed when third-party services need to verify tokens without the signing key. Switch to RS256 in EP-07+ if an external party needs to validate tokens.

### Why `jti` claim contains `session_id`?

The `jti` (JWT ID) binds the access token to its corresponding `sessions` row. On logout, the session_id is extracted from the JWT, allowing targeted session revocation without maintaining a token blocklist. Access tokens are still validated by expiry only — the session_id in `jti` is informational for logout; the session row is the source of truth for refresh tokens.

---

## Settings

All JWT settings are in `Settings` (app/config/settings.py):

| Field | Env Var | Default |
|-------|---------|---------|
| `jwt_secret` | `JWT_SECRET` | `""` (must be set in production) |
| `jwt_algorithm` | `JWT_ALGORITHM` | `"HS256"` |
| `jwt_access_token_expire_minutes` | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` |
| `jwt_refresh_token_expire_days` | `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` |

---

## Models

### Session (`sessions`)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID7 PK | `ses_` prefix external ID |
| user_id | UUID FK → users.id | ON DELETE CASCADE |
| refresh_token_hash | String(64) | SHA-256 hex of raw token |
| expires_at | DateTime(tz) | Hard expiry |
| revoked_at | DateTime(tz) NULL | NULL = active |
| ip_address | String(45) NULL | Supports IPv6 |
| user_agent | Text NULL | Browser/client fingerprint |

`is_revoked` property returns `revoked_at is not None`.

### VerificationToken (`verification_tokens`)

| Column | Type | Notes |
|--------|------|-------|
| user_id | UUID FK | ON DELETE CASCADE |
| token_hash | String(64) | SHA-256 hex |
| expires_at | DateTime(tz) | 24-hour window |
| used_at | DateTime(tz) NULL | NULL = unused |

### PasswordResetToken (`password_reset_tokens`)

Same structure as VerificationToken but with a 1-hour window. Existing unused tokens are invalidated before creating a new one.

### User (`users`) — new column

`password_hash: String(256) NULL` — stores the Argon2id PHC string. Nullable because existing users from OAuth flows will not have passwords.

---

## Auth Module Reference (`app/auth/`)

### `password.py`
- `hash_password(plain: str) -> str` — Argon2id hash
- `verify_password(hashed: str, plain: str) -> bool` — constant-time comparison
- `needs_rehash(hashed: str) -> bool` — true when parameters have changed

### `tokens.py`
- `create_access_token(*, user_id, session_id, email, settings) -> str`
- `decode_access_token(token, *, settings) -> dict` — raises `jwt.exceptions.*` on failure
- `generate_refresh_token() -> str` — 256-bit URL-safe random string
- `hash_token(raw: str) -> str` — SHA-256 hex digest

### `rbac.py`
- `Permission` — StrEnum with 13 granular permissions
- `ROLE_PERMISSIONS` — maps `MembershipRole` → `frozenset[Permission]`
- `has_permission(role, permission) -> bool`
- `get_permissions(role) -> frozenset[Permission]`

Role hierarchy (most → least privileged):
1. **OWNER** — all permissions
2. **ADMIN** — all except `org:delete`, `billing:write`
3. **MEMBER** — read/write access to projects, read-only org/providers/usage
4. **VIEWER** — read-only across all domains

### `exceptions.py`
- `AuthError` — base
- `InvalidCredentialsError` — bad email/password
- `AccountDisabledError` — disabled account
- `InvalidTokenError` — expired, used, or revoked token
- `EmailAlreadyVerifiedError` — email already verified

### `service.py — AuthService`

| Method | Description |
|--------|-------------|
| `login(email, password, ip_address, user_agent)` | Authenticate + create session |
| `logout(session_id)` | Revoke session |
| `refresh(refresh_token)` | Rotate token + issue new access token |
| `create_verification_token(user_id)` | Create email verification token (returns raw) |
| `verify_email(token)` | Consume verification token |
| `create_password_reset_token(email)` | Create reset token (returns raw, or None if user not found) |
| `reset_password(token, new_password)` | Consume reset token + update hash + revoke all sessions |

### `dependencies.py`

| Export | Type | Usage |
|--------|------|-------|
| `CurrentUser` | `Annotated[User, Depends(...)]` | `user: CurrentUser` in routes |
| `CurrentOrganization` | `Annotated[Organization, Depends(...)]` | requires `{org_id}` path param |
| `CurrentMembership` | `Annotated[Membership, Depends(...)]` | requires CurrentUser + CurrentOrganization |
| `RequirePermission(perm)` | `Callable → Depends(...)` | `_: RequirePermission(Permission.ORG_WRITE)` |

---

## API Endpoints

All under `/v1/auth/`:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/login` | None | Email+password login |
| POST | `/logout` | Bearer | Revoke current session |
| POST | `/refresh` | None | Rotate refresh token |
| POST | `/verify-email` | None | Consume verification token |
| POST | `/request-password-reset` | None | Request reset link (always 200) |
| POST | `/reset-password` | None | Consume reset token |

---

## Migration

Revision `d5e6f7a8b9c0` (revises `c3d4e5f6a7b8`):
1. `ALTER TABLE users ADD COLUMN password_hash VARCHAR(256)`
2. `CREATE TABLE sessions (...)`
3. `CREATE TABLE verification_tokens (...)`
4. `CREATE TABLE password_reset_tokens (...)`

---

## What EP-06 Should Build On

- `CurrentUser`, `CurrentOrganization`, `CurrentMembership`, `RequirePermission` are ready to use on any resource route
- `AuthService` handles the complete auth lifecycle; no changes expected unless adding OAuth
- `email_verified` on User is set by `verify_email()`; EP-06 email provider should call `create_verification_token()` on user registration
- `create_password_reset_token()` returns the raw token; EP-06 email provider should email it
- Consider rate-limiting `/login` and `/request-password-reset` endpoints in EP-06 (the interface for rate-limiting is deferred per F-023)
- Account lockout (F-023) was deferred; implement by adding `failed_login_attempts` and `locked_until` columns to `users`
