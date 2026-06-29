# Authentication Architecture — AI FinOps

## Token Strategy

### Access Tokens (JWT)

- **Algorithm:** HS256 (HMAC-SHA256) with `JWT_SECRET` environment variable
- **Lifetime:** 30 minutes (configurable via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Claims:** `sub` (user UUID), `jti` (session UUID), `email`, `iat`, `exp`, `type: "access"`
- **Validation:** Signature + expiry checked on every authenticated request
- **Not stored:** Stateless; no server-side record

### Refresh Tokens (Opaque)

- **Format:** `secrets.token_urlsafe(32)` — 256 bits of cryptographic randomness
- **Storage:** SHA-256(raw_token) in `sessions.refresh_token_hash`
- **Lifetime:** 30 days (configurable via `JWT_REFRESH_TOKEN_EXPIRE_DAYS`)
- **Rotation:** Every `/refresh` call replaces the stored hash atomically (replay detection)
- **Revocation:** Set `revoked_at` on the session row; next refresh attempt gets a DB miss

## Password Security

- **Algorithm:** Argon2id (PHC winner, OWASP recommended)
- **Parameters:** time_cost=3, memory_cost=65536 (64 MiB), parallelism=4, hash_len=32 (argon2-cffi defaults)
- **Storage:** PHC string in `users.password_hash`; never the raw password
- **Upgrade path:** `needs_rehash()` detects outdated parameters; rehash on next successful login

## One-Time Tokens (Email Verification, Password Reset)

Both use the same pattern:
1. Generate `secrets.token_urlsafe(32)` raw token
2. Store `hashlib.sha256(raw.encode()).hexdigest()` (64 hex chars) in the DB
3. Send the raw token to the user's email (email transport deferred to EP-06)
4. On consumption: verify hash match, check `used_at is None` and `expires_at > now`, then mark `used_at`

Password reset tokens are invalidated (marked used) when a new one is created, preventing parallel reset token abuse.

## RBAC

| Role | Key Permissions |
|------|----------------|
| OWNER | All permissions |
| ADMIN | org:read/write, org:manage_members, project:*, provider:*, usage:read, billing:read |
| MEMBER | org:read, project:read/write, provider:read, usage:read |
| VIEWER | org:read, project:read, provider:read, usage:read |

Permission checks use `has_permission(role, permission)` which reads from a compile-time `frozenset` mapping — no DB query required.

## Security Considerations

- **JWT secret** must be at least 32 chars; `Settings` enforces non-empty in production
- **No secrets in logs:** `jwt_secret`, `postgres_password` are `SecretStr` and excluded from repr
- **Email enumeration prevention:** `/request-password-reset` always returns HTTP 200
- **Session binding:** The `jti` claim links each access token to a `sessions` row, enabling targeted logout
- **Cascade deletes:** `sessions`, `verification_tokens`, `password_reset_tokens` use `ON DELETE CASCADE` so user deletion cleans up all auth data
- **IPv6 support:** `ip_address` column is `VARCHAR(45)` to hold full IPv6 addresses

## Deferred Controls

- Rate limiting on `/login` and `/request-password-reset`
- Account lockout after repeated failed logins
- Access token revocation blocklist
- Audit log for authentication events
