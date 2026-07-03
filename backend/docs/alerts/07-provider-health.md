# Provider Health — EP-19.3 (honest scoping)

The ticket asks for `provider_error`/`provider_recovery` alert types, a
live provider-health indicator with "last failure, recovery time, failure
count," and a `Healthy`/`Warning`/`Critical`/`Recovering` status model.

## What was built

**Schema, additive**: `provider_connections` gained a
`ProviderHealthStatus` enum (`unknown`/`healthy`/`warning`/`critical`/
`recovering`) and four columns — `health_status`, `last_failure_at`,
`last_recovery_at`, `consecutive_failure_count` — all nullable/
zero-defaulted, so every existing row degrades safely to "unknown, never
checked." This is a genuinely useful, correctly-designed schema for a
*future* org-scoped connection-health feature.

**Alert types, defined**: `PROVIDER_ERROR`/`PROVIDER_RECOVERY` exist in
`AlertType`, mapped in `AlertService._EVENT_TYPE_MAP` to the EP-19.1
`EventType.PROVIDER_ERROR`/`PROVIDER_RECOVERY` values (which already
existed, unemitted, since EP-19.1).

## What was deliberately NOT built, and why

**No trigger wired.** The only related backend endpoint is
`POST /v1/providers/{provider}/test` (`app/api/v1/providers.py`):

```python
async def test_connection(provider: str, _user: CurrentUser) -> TestConnectionResponse:
```

It takes **no organization context** and **persists nothing** — it tests
platform-level/env-configured credentials via `_make_config_with_key()`
and returns a transient result. `grep -rln "ProviderConnection"
app/api/v1/*.py` returns zero files: **no API endpoint anywhere in this
codebase reads or writes a `ProviderConnection` row.** There is no
real, per-organization "is this provider currently healthy" signal
anywhere in this backend to trigger an alert from.

**No live health widget on the frontend.** The Connections page
(`frontend/src/features/Connections.tsx`) already calls this same
transient test endpoint on a manual "Test connection" click — this EP did
not add a new component that *looks* continuously live but is actually
polling nothing, because that would misrepresent what the system
actually knows. A widget with a green/red dot implies monitoring; this
backend does not monitor anything per-org today.

## What a real implementation would need

1. A `ProviderConnection` row per org+provider (doesn't exist today — the
   Connections page has no backend-side persistence at all, from an
   earlier EP, not this one).
2. An org-scoped variant of the test endpoint (or a background job) that
   writes `health_status`/`last_failure_at`/`consecutive_failure_count`
   onto that row.
3. `AlertService.fire(AlertType.PROVIDER_ERROR, ...)` called from that
   write path, with `provider_scope(provider_name)` as the dedup scope —
   the dedup/suppression modules already support this out of the box,
   since they're alert-type-agnostic.

This is scoped, sized, and ready to build in a future EP — the schema
this EP shipped is exactly what step 2 needs.
