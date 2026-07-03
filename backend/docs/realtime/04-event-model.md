# Event Model — `RealtimeEvent`

Defined in `app/realtime/events.py`. Every event on every channel — SSE or
WebSocket — is this one shape, so clients need exactly one parser.

```json
{
  "event_id": "0d3f2b1e-...-uuid",
  "timestamp": "2026-07-03T12:00:00Z",
  "organization_id": "b2a1c3d4-...-uuid",
  "type": "usage.created",
  "version": 1,
  "payload": { "...": "type-specific fields" },
  "trace_id": "req_abc123",
  "correlation_id": null
}
```

| Field | Type | Notes |
|---|---|---|
| `event_id` | UUID | Generated per event; used as the SSE `id:` field and as the `Last-Event-ID` reconnect cursor. |
| `timestamp` | ISO-8601 datetime, UTC | When the event was constructed, not necessarily when the underlying action happened. |
| `organization_id` | UUID | Which organization this event belongs to — the field `ConnectionManager.dispatch()` uses to enforce isolation. |
| `type` | `EventType` (string enum) | See the table below. |
| `version` | integer | Currently always `1` (`CURRENT_EVENT_VERSION`). Bumped only on a breaking payload-shape change for a given `type`. |
| `payload` | object | Type-specific fields — see below. |
| `trace_id` | string \| null | Carried through from the request that produced the event (e.g. the ingestion `request_id`) so a live event can be correlated with the originating log line/record. Never generated fresh by the event bus. |
| `correlation_id` | string \| null | Reserved for chaining related events (e.g. a budget-exceeded event correlated with the usage event that triggered it). Not populated by anything in this EP — the field exists so a later EP can use it without a schema change. |

## Event types

Twelve types are defined (`EventType` in `app/realtime/events.py`), matching
the ticket's list exactly. **Only `usage.created` is actually emitted by
this EP** — see the honesty note below.

| `type` | Emitted in this EP? | Trigger |
|---|---|---|
| `usage.created` | **Yes** | `POST /v1/ingest/usage` after a non-duplicate record is stored (`app/api/v1/ingest.py`) |
| `usage.updated` | No | No code path updates a stored usage record after ingestion |
| `budget.threshold_reached` | No | No budget-monitoring service exists yet |
| `budget.exceeded` | No | No budget-monitoring service exists yet |
| `provider.error` | No | No provider-health-monitoring service exists yet |
| `provider.recovery` | No | No provider-health-monitoring service exists yet |
| `api_key.created` | No | `OrganizationApiKeyService` (EP-14) is not wired to the event bus |
| `api_key.deleted` | No | Same as above |
| `sdk.connected` | No | No SDK connect/disconnect tracking exists in the backend |
| `sdk.disconnected` | No | Same as above |
| `organization.updated` | No | Organization update endpoints are not wired to the event bus |
| `notification.created` | No | No backend notification-creation service exists (the frontend's notification center is client-derived, per EP-13's audit notes) |

**Why define eleven types nobody emits?** So the wire format and every
client SDK are forward-compatible: a client written against this EP's
`EventType` enum needs no changes when a later EP adds the trigger logic
for (say) `budget.exceeded` — it will simply start receiving events of a
type it already knows how to route. Defining the enum member is not the
same as building fake trigger logic; nothing in this EP synthesizes an
event of a type with no real source, which would have been dishonest
about what actually works today.

## `usage.created` payload

The only payload shape actually populated. From
`app/api/v1/ingest.py::ingest_usage()`:

```json
{
  "usage_id": "5b1e2b2e-...-uuid",
  "provider": "openai",
  "model": "gpt-4.1",
  "cost": "0.08120000",
  "currency": "USD",
  "total_tokens": 1520,
  "status": "success",
  "project_id": "b2a1c3d4-...-uuid"
}
```

`cost` is a decimal-string (not a JSON number) to avoid floating-point
precision loss — the same convention as the existing usage/analytics
APIs use for currency amounts.

## Versioning

`version` starts at `1` for every type. If a type's payload shape ever
needs a breaking change, bump `version` for that emission and document
both shapes in this file — clients should switch on `(type, version)`,
not `type` alone, once more than one version exists. As of this EP, only
version `1` exists for any type.
