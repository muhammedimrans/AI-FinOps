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
- **Member management API** — needed to build the Users page:
  `GET/POST/PATCH/DELETE /v1/organizations/{org_id}/members` and
  `/invitations`. The membership + role model already exists.
- **RBAC read/write API** — the enforcement engine (EP-05) exists but has no
  endpoint to read roles/permissions or change a member's role:
  `GET /v1/rbac/roles`, `GET /v1/rbac/permissions`,
  `PUT /v1/organizations/{org_id}/members/{id}/role`.
- **API-key issuance API** — `GET/POST/DELETE /v1/organizations/{org_id}/api-keys`.
  Until it exists, the Settings "API Keys" section is a labeled preview.
- **Audit-log query API** — `GET /v1/organizations/{org_id}/audit-logs`.
  Structured audit logging exists server-side but isn't queryable.
- Provider health/latency endpoint to replace static "Active" badges on the
  Providers page. (The Connections page already surfaces real per-provider
  health/latency via the on-demand `POST /providers/{p}/test`.)

## Medium

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
