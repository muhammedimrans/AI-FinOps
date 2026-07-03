# Security Review — EP-19.3 Alert Engine

Reviewed against the ticket's checklist. Each item states what was
verified and where the evidence lives.

## Cross-tenant isolation ("no notification leakage")

**Verified at three layers.**

1. **Persistence**: every `Alert`/`AlertRule`/`AlertPreference`/
   `AlertSuppression` row carries `organization_id`, and every repository
   query filters on it (`AlertRepository.list_for_org`,
   `AlertRuleRepository.list_enabled_for_type`, etc. — see
   `app/repositories/alert_repository.py`).
2. **API layer**: every `app/api/v1/alerts.py` endpoint takes
   `organization_id` as a required query parameter, verified via
   `RequireQueryPermission` (a new dependency factory in
   `app/auth/dependencies.py`, the query-param equivalent of the existing
   path-param `RequirePermission`) — which resolves membership through
   `get_query_org_membership()`, the same function `app/api/v1/
   dashboard.py` already uses. Every mutation (`acknowledge`/`resolve`/
   `dismiss`/`reopen`, rule/suppression delete) additionally re-checks
   `resource.organization_id == organization_id` **after** lookup and
   before acting — a client cannot mutate another organization's alert by
   guessing its UUID, even with valid membership in *some* organization.
   Verified: `tests/test_ep19_3.py::test_cross_org_alert_is_404_not_leaked`
   and `test_delete_rule_cross_org_is_404` — both assert **404, not
   200/403** (no leakage of existence).
3. **Delivery**: alerts are published via the exact same
   organization-scoped `EventBus`/`ConnectionManager` EP-19.1 already
   proved isolated (see `docs/realtime/SECURITY_REVIEW.md`'s "Cross-tenant
   isolation" section) — this EP adds no new delivery path, so no new
   isolation surface to audit there.

## Authentication & authorization

**Reused, not reimplemented.** `NOTIFICATION_READ`/`NOTIFICATION_WRITE`
were added to the existing `Permission` enum
(`app/auth/rbac.py`) and granted through the existing
`ROLE_PERMISSIONS` table — OWNER/ADMIN/MEMBER get both, VIEWER gets only
`NOTIFICATION_READ`. No new JWT validation, no new session model, no new
role system. `RequireQueryPermission` composes with
`get_current_user`/`get_query_org_membership` exactly as
`RequirePermission` composes with `_get_current_membership`.

## No secrets in alert data

`Alert.alert_metadata` (mapped to the DB column `metadata`) is documented
at the schema level — `comment="Never store secrets here — provider
names, amounts, ids only."` — and every call site was audited:

- `_check_budget_alerts()` (`app/api/v1/ingest.py`): metadata is
  `project_id`, `project_name`, `pct_used`, `budget`, `month_to_date` —
  no credentials.
- `invite_member`/`remove_member` (`app/api/v1/organizations.py`):
  metadata is `email`, `role` — no credentials.
- `create_api_key`/`delete_api_key`: metadata is `api_key_id`, `name`,
  `prefix` — **explicitly excludes `raw_key`**, matching this codebase's
  existing "the raw key is never persisted or logged anywhere" discipline
  (see the module docstring in `organizations.py`).

## Denial-of-service / resource exhaustion

- `AlertRepository.list_for_org()` caps `limit` at 200 server-side
  regardless of what a client requests.
- Dedup means a single misbehaving source firing the same underlying
  condition thousands of times produces **one** row with an incrementing
  counter, not thousands of rows — directly mitigating the ticket's
  "100,000 alerts/day" scale concern for any one repeated condition.
- Every alert-firing call site (`ingest.py`'s `_check_budget_alerts`,
  `organizations.py`'s `_fire_alert_safely`) wraps `AlertService.fire()`
  in a try/except that logs and swallows — an alerting bug can never
  fail the primary request (ingestion, membership, API-key mutation) that
  triggered it. `EventBus.publish()` itself also never raises (EP-19.1's
  own contract), so a Redis outage degrades to "no live delivery," not
  "requests start failing."

## What this review does not claim

This EP does not add new input-validation surface beyond standard Pydantic
schema validation already used everywhere else in this backend (see
`app/schemas/alerts.py`) — no raw SQL, no dynamic query construction from
user input (`AlertRepository.list_for_org`'s search filter uses
SQLAlchemy's parameterized `.ilike()`, not string interpolation).
