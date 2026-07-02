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
- Short-lived HS256 access tokens; production startup fails on missing/weak `JWT_SECRET` or `APP_SECRET_KEY`
- Role-based access control (RBAC) with per-permission dependencies
- Secrets typed as `SecretStr` so they never appear in logs; structured audit logging
- Anti-enumeration responses on password reset

Known gaps (tracked in [ROADMAP.md](ROADMAP.md)):
- Dashboard/analytics endpoints validate the JWT but do not yet verify org
  membership against the `organization_id` query parameter (EP-11)
- No rate limiting on authentication endpoints
- Refresh tokens are persisted in browser localStorage (httpOnly cookie migration planned)
