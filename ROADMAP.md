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
- Real notifications feed (anomaly alerts) behind the header bell
- Wire Settings sections that are currently local-only (API keys, org preferences) to backend APIs
- Provider health/latency endpoint to replace static "Active" badges on the Providers page

## Medium

- Cost forecasting endpoint + Monthly Forecast dashboard widget
- Hourly usage granularity (enables usage heatmaps)
- E2E test suite (Playwright) and visual regression coverage
- API reference generation from OpenAPI into `docs/API/`

## Low

- Populate placeholder doc sections (ADRs, diagrams, user guides)
- SDK packages (`sdk/`), provider adapter packages (`provider-adapters/`),
  and example apps (`examples/`) are currently scaffolds — build or remove
