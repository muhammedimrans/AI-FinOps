# Roadmap

High-level, ordered by priority. See `docs/knowledge/` for per-episode status reports.

## Critical (pre-production)

- **Org-scoped authorization (EP-11)** — enforce membership between the
  authenticated user and the `organization_id` used by dashboard/analytics
  endpoints. Today any valid JWT can query any org's aggregates.
- **Rate limiting** on `/v1/auth/*` (credential stuffing) and dashboard queries.

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
