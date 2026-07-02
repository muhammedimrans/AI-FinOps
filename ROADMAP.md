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
  session), proving the flow end-to-end.
- ~~Usage ingestion endpoint~~ — **done (EP-16)**: `POST /v1/ingest/usage`,
  authenticated by an Organization API Key with `usage:write`. Validates,
  deduplicates by `request_id` (never double-counts, even under concurrent
  retries), stores a `usage_records` row, and feeds the existing EP-08/EP-09
  tables so Overview/Analytics/Providers/Models/Projects reflect ingested
  usage immediately with zero frontend or dashboard-endpoint changes.
  **Not yet done**: no SDKs, no Monitoring Agent, no per-key rate limiting.
- **Audit-log query API** — `GET /v1/organizations/{org_id}/audit-logs`.
  Structured audit logging exists server-side but isn't queryable.
- Provider health/latency endpoint to replace static "Active" badges on the
  Providers page. (The Connections page already surfaces real per-provider
  health/latency via the on-demand `POST /providers/{p}/test`.)

## Medium

- **EP-16 Phase 2 — Monitoring Agent, SDKs, CLI**: `POST /v1/ingest/usage`
  and its auth are done; nothing yet actually *calls* it from a real
  integration. Also still open: per-key rate limiting on the ingest
  endpoint specifically (the login rate limiter's sliding-window approach
  is the obvious template) and a Redis/in-memory cache in front of the API
  key hash lookup if per-key traffic ever justifies it (no caching exists
  yet — every authenticated request does 2 SELECTs + 1 UPDATE, and
  ingestion adds 2 more SELECTs + up to 3 more writes on top of that for
  the dashboard-table feed).
- Batch/bulk ingestion (`POST /v1/ingest/usage/batch`) — explicitly out of
  scope for EP-16, which only accepts one record per request.
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
