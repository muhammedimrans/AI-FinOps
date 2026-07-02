# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
("Report a vulnerability" on the repository's Security tab). Do **not** open a
public issue for security reports.

We aim to acknowledge reports within 72 hours.

## Supported Versions

This project is pre-1.0. Only the latest commit on `main` receives security fixes.

## Security Posture (current state)

Implemented:
- Argon2id password hashing; opaque refresh tokens stored as SHA-256 hashes with rotation on use
- Short-lived HS256 access tokens with required-claims validation, 30s clock-skew
  leeway, algorithm pinned to HMAC variants; production startup fails on
  missing/weak `JWT_SECRET` or `APP_SECRET_KEY`
- Access-token revocation: logout / password reset invalidate the session, and
  every request verifies the token's session is still active
- Org-membership enforcement on every organization-scoped endpoint — client
  supplied `organization_id` values are never trusted (403/404 semantics)
- Login rate limiting: per-IP sliding window plus per-account temporary lockout
  with exponential backoff (Redis-backed, in-memory fallback)
- Security response headers (CSP, nosniff, frame denial, referrer policy,
  HSTS in production; auth responses are no-store)
- Role-based access control (RBAC) with per-permission dependencies
- Secrets typed as `SecretStr` so they never appear in logs; structured audit logging
- Anti-enumeration responses on password reset

Known gaps (tracked in [ROADMAP.md](ROADMAP.md)):
- Refresh tokens are persisted in browser localStorage (httpOnly cookie migration planned)
- Role/permission granularity on org-scoped reads is membership-only (any role can read)
- `POST /v1/pricing/models` requires auth but not yet BILLING_WRITE RBAC
