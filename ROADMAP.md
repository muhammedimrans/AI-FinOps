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
  display prefix. **Not yet done**: nothing authenticates inbound requests
  with one of these keys — see EP-14 Phase 2 below.
- **Audit-log query API** — `GET /v1/organizations/{org_id}/audit-logs`.
  Structured audit logging exists server-side but isn't queryable.
- Provider health/latency endpoint to replace static "Active" badges on the
  Providers page. (The Connections page already surfaces real per-provider
  health/latency via the on-demand `POST /providers/{p}/test`.)

## Medium

- **EP-14 Phase 2 — usage ingestion via API keys**: authenticate an inbound
  request with an `organization_api_key` (the service already has
  `validate_key()` / `touch_last_used()` ready for this), enforce the key's
  granted `permissions` scopes, rate-limit per key, and record `last_used_at`
  on each authenticated call. No SDKs or provider integrations are in scope
  for that phase either — see EP-14's own remaining-work notes.
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
