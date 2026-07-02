# Roadmap

High-level, ordered by priority. See `docs/knowledge/` for per-episode status reports.

## Critical (pre-production)

- ~~Org-scoped authorization~~ — **done**: membership is enforced on every
  org-scoped endpoint (dashboard, analytics, usage, pricing).
- ~~Rate limiting on login~~ — **done**: sliding window + account lockout.
- Role-based (not just membership-based) permissions on org-scoped reads/writes;
  BILLING_WRITE enforcement on pricing creation.

## High

- Refresh-token storage migration: localStorage → httpOnly SameSite cookie
- ~~Password reset / email verification UI~~ — **done**: `/forgot-password`,
  `/reset-password`, `/verify-email` wired to the EP-05 endpoints.
- ~~Notifications feed behind the header bell~~ — **done (client-derived)**:
  alerts computed live from budget + spend data. A server-side feed can
  replace the `useAlerts` hook without UI changes.
- ~~Member management API~~ — **done (EP-13)**:
  `GET/POST/PATCH/DELETE /v1/organizations/{org_id}/members`, wired to a real
  Users page (invite, role change, remove; last-owner and privilege-
  escalation guards).
- ~~RBAC read API~~ — **done (EP-13)**: `GET /v1/rbac/roles`,
  `GET /v1/rbac/permissions`, wired to a real RBAC page (role cards +
  permission matrix). Role *editing* is done via the member-role endpoint
  above, not a separate RBAC write endpoint.
- ~~API-key issuance API~~ — **done (EP-14 Phase 1)**:
  `GET/POST/DELETE /v1/organizations/{org_id}/api-keys`, wired to a real API
  Keys page (create with scoped permissions + expiration, one-time secret
  reveal, revoke). The raw key is never persisted — only a SHA-256 hash and a
  display prefix.
- ~~API-key authentication middleware~~ — **done (EP-15)**: `CurrentApiKey`
  and `RequireApiKeyPermission` (`app/auth/api_key_auth.py`) validate
  `Authorization: Bearer costorah_live_...` end-to-end (hash lookup, expiry,
  organization status, granted scopes, `last_used_at`) and are ready for any
  future endpoint to depend on. `GET /v1/organizations/{org_id}/api-keys`
  is the first endpoint wired to accept it (alongside the existing JWT
  session), proving the flow end-to-end. **Not yet done**: no endpoint
  other than that one GET actually requires an API key yet — see EP-15
  Phase 2 (usage ingestion) below.
- **Audit-log query API** — `GET /v1/organizations/{org_id}/audit-logs`.
  Structured audit logging exists server-side but isn't queryable.
- Provider health/latency endpoint to replace static "Active" badges on the
  Providers page. (The Connections page already surfaces real per-provider
  health/latency via the on-demand `POST /providers/{p}/test`.)

## Medium

- **EP-15 Phase 2 — usage ingestion via API keys**: the authentication
  middleware is done (EP-15); what's missing is an actual ingestion
  endpoint that requires `CurrentApiKey`/`RequireApiKeyPermission` and does
  something with the request (write usage events). Also still open:
  per-key rate limiting (the login rate limiter's sliding-window approach
  is the obvious template) and a Redis/in-memory cache in front of the
  hash lookup if per-key traffic ever justifies it (no caching exists yet —
  every authenticated request still does 2 SELECTs + 1 UPDATE). No SDKs or
  provider integrations are in scope for that phase either.
- Server-side cost forecasting + anomaly detection endpoints. The Analytics
  page ships an **in-app** linear forecast and rolling-σ anomaly detector
  (labeled as client-side); a server model would improve accuracy and enable
  alerting independent of an open browser.
- Hourly usage granularity (enables usage heatmaps)
- Support-ticket submission endpoint (the Support contact form is a labeled preview)
- E2E test suite (Playwright) and visual regression coverage
- API reference generation from OpenAPI into `docs/API/`

## Low

- Populate placeholder doc sections (ADRs, diagrams, user guides)
- SDK packages (`sdk/`), provider adapter packages (`provider-adapters/`),
  and example apps (`examples/`) are currently scaffolds — build or remove
