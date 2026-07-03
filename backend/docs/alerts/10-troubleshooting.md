# Troubleshooting — EP-19.3

## "I created a budget-threshold rule and nothing fired"

Checklist, in order:

1. **Does the project have a `budget` set?** `Project.budget` is `NULL`
   by default — `_check_budget_alerts()` returns immediately if
   `project.budget is None or project.budget <= 0` (deliberate: no
   fabricated default threshold).
2. **Is the rule `enabled`?** `RuleEngine.evaluate_type()` only loads
   `enabled=True` rows.
3. **Is the threshold actually crossed?** The value compared is
   *percentage of budget used this month* (`month_to_date / budget *
   100`), not a raw dollar amount — a `threshold: "90"` rule with
   `operator: "gte"` fires at 90% used, not $90 spent.
4. **Is there an active suppression?** Check
   `GET /v1/alerts/suppressions?organization_id=...` — an
   `ORGANIZATION`-scoped or `budget_threshold`-typed suppression window
   silently prevents firing (correctly — see `06-suppression.md`).
5. **Did ingestion actually happen for that project?** The check only
   runs inside `POST /v1/ingest/usage` when `record.project_id is not
   None` — an ingestion with no `project_id` never triggers a budget
   check.

## "I fired 50 identical alerts but only see 1"

This is deduplication working as designed, not a bug — see
`05-deduplication.md`. Check `occurrence_count` on the one row; it should
read 50. If you need genuinely separate alerts, use a different `scope`
value per occurrence (the dedup key is a hash of `alert_type:scope`).

## "provider_error/provider_recovery never fires"

Expected — see `07-provider-health.md`. There is no real per-org
provider-health signal in this backend today; these alert types are
defined for forward compatibility only, exactly like several
never-emitted `EventType` values from EP-19.1.

## "Acknowledge/resolve/dismiss returns 409"

Check the alert's current `status` first (`GET /v1/alerts?...`) — each
transition is status-guarded:

| Action | Valid from |
|---|---|
| `acknowledge` | `open` only |
| `resolve` | `open` or `acknowledged` |
| `dismiss` | `open` or `acknowledged` |
| `reopen` | anything except `open` |

A 409 means the transition doesn't apply to the alert's current state,
not a system failure.

## "I get 404 acknowledging an alert I can see in another tab"

Almost always an organization mismatch: `organization_id` in the request
query string must match the alert's own `organization_id`. This is
intentional (see the security review's cross-tenant isolation section) —
a 404 here means "not found for this organization," which is the correct,
non-leaking response even if the alert exists under a different org the
caller also belongs to.

## "The notification center shows an alert with a generic title like 'Organization updated'"

The event's own `title`/`severity` (from `AlertService._publish()`'s
payload) should override the generic per-event-type copy in
`frontend/src/hooks/useAlerts.ts`'s `EVENT_COPY` map — if you see the
generic fallback, check that the live event's `payload.title` field is
actually present (older/malformed events, or a future new alert type not
yet added to `_EVENT_TYPE_MAP` in `dispatcher.py`, would fall back to
this).

## "Metrics for the alert engine aren't showing up on `/metrics`"

`app.alerts.metrics.render_alerts_metrics()` is appended as a **third**
block on `GET /metrics`, after the static payload and the EP-19.1
realtime block (see `app/api/v1/health.py`). If a metric name you expect
isn't there, confirm the counter was actually incremented somewhere in
the request path you tested — `alerts_acknowledged_total` only increments
via `POST /v1/alerts/{id}/acknowledge`, for example, not via direct
repository/model manipulation in a script.

## Where to look next

- Backend: `app/alerts/` (engine), `app/api/v1/alerts.py` (REST API),
  `app/repositories/alert_repository.py` (data access).
- Tests: `backend/tests/test_ep19_3.py` (61 tests) — the fastest way to
  see exact expected behavior for any of the above.
- Frontend: `frontend/src/hooks/useAlerts.ts`,
  `frontend/src/hooks/useAlertsHistory.ts`,
  `frontend/src/layouts/Header.tsx` (notification panel).
