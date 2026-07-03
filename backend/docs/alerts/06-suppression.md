# Suppression — EP-19.3

`app/alerts/suppression.py` + `AlertSuppression` model, checked first
inside `AlertService.fire()` — before dedup, before persistence.

## Three scopes

| Scope | `target` | Matches |
|---|---|---|
| `ORGANIZATION` | `NULL` (ignored) | Every alert type, org-wide — e.g. a planned maintenance window |
| `ALERT_TYPE` | An `AlertType` value | Only that alert type |
| `PROVIDER` | A provider slug | Only when the firing alert names that provider |

Checked in that order by `is_suppressed()`; the first match wins and its
row is returned (or `None` if nothing applies). A suppression is time-
bounded: `starts_at <= now AND (ends_at IS NULL OR ends_at >= now)` —
`ends_at = NULL` means "active until explicitly cleared," matching the
ticket's "indefinite maintenance window" case.

## What suppression does — and doesn't — do

If `is_suppressed()` returns a match, `AlertService.fire()`:

- Increments `alerts_suppressed_total{alert_type}` — the occurrence is
  **counted**, not silently dropped.
- Returns `None` — **no `Alert` row is created or updated**, and no
  `RealtimeEvent` is published.

This means a suppressed alert never reaches the notification center at
all, by design ("don't create/deliver a notification" — not "pretend
this never happened," which is why the metric still increments even
though nothing is persisted).

## API

`GET`/`POST /v1/alerts/suppressions`, `DELETE /v1/alerts/suppressions/{id}`
— all `organization_id`-scoped, gated by `notification:write` for
mutations. `DELETE` soft-deletes the row, which ends the suppression
immediately (a soft-deleted row is excluded from `list_active()`'s query,
which filters `deleted_at IS NULL`).

```json
POST /v1/alerts/suppressions?organization_id=org_1
{
  "scope": "organization",
  "reason": "Scheduled maintenance 2026-07-10 02:00-04:00 UTC"
}
```

```json
POST /v1/alerts/suppressions?organization_id=org_1
{
  "scope": "provider",
  "target": "openai",
  "ends_at": "2026-07-05T00:00:00Z",
  "reason": "Known OpenAI outage, tracked separately"
}
```

## Test coverage

`tests/test_ep19_3.py::TestSuppression` — one test per scope (no
suppressions active → `None`; organization scope always matches;
alert-type scope matches only that type; provider scope requires an
explicit provider match, with no-provider and wrong-provider cases both
asserted `None`).
