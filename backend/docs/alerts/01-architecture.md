# Alert Architecture — EP-19.3

## Where this sits

```
SDK → Usage API → Redis Event Bus → Realtime Gateway → Dashboard → Notification Center
                        ▲                                                  ▲
                        │                                                  │
                 EventBus.publish()                              live WS delivery
                        │                                                  │
        ┌───────────────┴────────────────┐                                │
        │         Alert Engine (NEW)     │                                │
        │  Rule Engine → Dispatcher      │────── AlertService._publish() ─┘
        │  (dedup + suppression applied) │
        └───────────────┬─────────────────┘
                         │ persists
                         ▼
                  alerts / alert_rules / alert_preferences /
                  alert_suppressions  (Postgres, additive tables)
```

This EP adds one new layer — `backend/app/alerts/` — on top of the
telemetry platform EP-19.1/EP-19.2 already shipped. It reuses, and never
rewrites:

- **EventBus** (`app/realtime/event_bus.py`) for delivery — an alert is
  published as the exact same `RealtimeEvent` envelope every other event
  type uses, flowing through the same organization-scoped Redis channel
  and the same WebSocket/SSE gateways.
- **Frontend notification center** (EP-19.2) — it already merged live
  notification-shaped events into its alert list; this EP is the trigger
  that makes that merge actually produce alerts, plus a new search/filter/
  archive layer and a persisted-history REST API.
- **Auth, RBAC, organization membership** — two new permissions
  (`notification:read`/`notification:write`) added to the existing
  `Permission` enum, granted the same way `api_key:read`/`write` already
  is. No new authentication system.

## New components (`app/alerts/`)

| Module | Responsibility |
|---|---|
| `conditions.py` | Pure comparison (`gt`/`lt`/`eq`/`gte`/`lte`) + composable AND/OR/NOT tree |
| `rule_engine.py` | Loads an org's enabled `AlertRule` rows for one alert type, matches against a computed value |
| `dedup.py` | Groups repeated occurrences of "the same underlying problem" into one row with an occurrence counter |
| `suppression.py` | Checks org-wide / alert-type / provider suppression windows |
| `dispatcher.py` | `AlertService` — the single entry point every trigger calls: suppress → dedup → persist → publish |
| `preferences.py` | Per-user severity threshold, quiet hours, enabled-type allow-list (applied at read time) |
| `metrics.py` | Prometheus counters/histograms, own `CollectorRegistry`, appended to `GET /metrics` |

## New tables (all additive — see `20260703_1733_b4a66af65de9_ep19_3_alert_engine.py`)

`alert_rules`, `alerts`, `alert_preferences`, `alert_suppressions` — plus
two purely-additive columns: `projects.budget` and four health-tracking
columns on `provider_connections`. No existing table, column, or index
was modified or renamed.

## Honest accounting of the 18 ticket-named alert types

Of 18 `AlertType` values, **6 have a real, organization-scoped trigger**
wired into an existing code path today:

| Alert type | Trigger |
|---|---|
| `budget_threshold` / `budget_exceeded` | `POST /v1/ingest/usage` — evaluated against month-to-date project spend on every ingestion |
| `org_member_added` / `org_member_removed` | `POST`/`DELETE /v1/organizations/{id}/members` |
| `api_key_created` / `api_key_revoked` | `POST`/`DELETE /v1/organizations/{id}/api-keys` |

The remaining **12** (`daily_spend_spike`, `hourly_spend_spike`,
`provider_error`, `provider_recovery`, `sdk_offline`, `sdk_reconnected`,
`api_key_expired`, `high_latency`, `rate_limit_spike`,
`large_cost_increase`, `usage_ingestion_failure`,
`webhook_delivery_failure`) are defined in `AlertType` for forward
compatibility — exactly like EP-19.1's own unemitted `EventType` values —
but have **no real signal source in this backend today**. Notably,
`provider_error`/`provider_recovery` were investigated and deliberately
left unwired: the only related endpoint
(`POST /v1/providers/{provider}/test`) takes no organization context and
persists no `ProviderConnection` row, so there is nothing per-org to
trigger from. The `ProviderConnection.health_status` columns this EP adds
exist for a *future* org-scoped connection-test endpoint, not this one.

## Success-criterion flow (verified, see the security review + tests)

Budget exceeds 90% → `RuleEngine.evaluate_type()` matches an enabled rule
→ `AlertService.fire()` persists (with dedup/suppression applied) →
`EventBus.publish()` → WebSocket delivery → `useAlerts()` merges the live
event → unread badge increments → user calls
`POST /v1/alerts/{id}/acknowledge` → `AlertTimeline` reflects the new
step → alert status becomes `acknowledged`. No polling anywhere in this
path.
