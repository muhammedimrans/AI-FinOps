# Real-Time Architecture — EP-19.1

## Why this exists

Before this EP, COSTORAH's only way to see new usage data was to poll:
`SDK → Usage API → Queue → Database → Dashboard (polling)`. EP-19.1 adds an
event-driven path alongside that one — it does not replace it. Every
existing polling endpoint (`GET /v1/usage/*`, `GET /v1/dashboard/*`, etc.)
is unchanged and keeps working exactly as it did before this EP.

```
                    ┌────────────────────────────┐
POST /v1/ingest/usage│  UsageIngestionService     │
   (unchanged)       │  (stores to usage_records, │
        │            │   unchanged schema)        │
        │            └──────────────┬─────────────┘
        │                           │ publish()
        │                           ▼
        │                  ┌─────────────────┐
        │                  │    EventBus      │  Redis PUBLISH +
        │                  │ (app/realtime/   │  bounded replay list
        │                  │  event_bus.py)   │  realtime:org:<uuid>
        │                  └────────┬─────────┘
        ▼                           │ PSUBSCRIBE realtime:org:*
┌───────────────┐         ┌─────────▼──────────┐
│ Existing       │         │  ConnectionManager  │  one per backend
│ polling APIs   │         │ (app/realtime/       │  process, started in
│ (unchanged)    │         │  connection_manager) │  AppContainer.create()
└───────────────┘         └─────────┬───────────┘
                                     │ per-connection
                                     │ asyncio.Queue
                       ┌─────────────┼─────────────┐
                       ▼             ▼             ▼
                  WebSocket       SSE           (future SDK
                  GET /v1/ws   GET /v1/events    push channel)
```

## Design constraints this EP was built under

The ticket was explicit: *do not rewrite any existing Engineering
Package*. Every piece below is a reuse of something already in the
codebase, not a new system:

| Need | Reused | New code |
|---|---|---|
| Message transport | Redis (`app.core.redis`, already a container dependency) | `EventBus` — pub/sub + replay list on top of the existing client |
| Auth | `decode_access_token`, `ApiKeyAuthService.authenticate`, RBAC `has_permission` | `app/realtime/auth.py` — pulls a token out of a WS/SSE request instead of an HTTP header dependency, then calls the same validation functions |
| Storage | `usage_records` table, unchanged | none — no new tables, no migration |
| Ingestion pipeline | `UsageIngestionService.ingest()`, unchanged | one `event_bus.publish(...)` call added after a successful (non-duplicate) ingest |

## Components

- **`app/realtime/events.py`** — the `RealtimeEvent` envelope and the
  `EventType` enum. See [Event Model](./04-event-model.md).
- **`app/realtime/event_bus.py`** — `EventBus`: publishes to a
  per-organization Redis channel (`realtime:org:<uuid>`) and maintains a
  bounded replay buffer (last 200 events, 1h TTL) for SSE reconnects.
- **`app/realtime/connection_manager.py`** — `ConnectionManager`: the
  single process-wide consumer of `EventBus.subscribe_all_organizations()`
  (one `PSUBSCRIBE realtime:org:*` per backend replica, not per client),
  fanning events out to that replica's locally-connected WebSocket/SSE
  clients via bounded per-connection queues.
- **`app/realtime/auth.py`** — `authenticate_realtime_connection()`: the
  single entry point both gateway endpoints call to validate a JWT or API
  Key and resolve which organization a connection is allowed to join.
- **`app/realtime/rate_limit.py`** — `ConnectionRateLimiter`: per-IP
  connection-attempt limiting (30/min by default), Redis-backed with an
  in-memory fallback.
- **`app/realtime/metrics.py`** — real `prometheus_client` metrics,
  appended to the existing `GET /metrics` payload.
- **`app/api/v1/realtime.py`** — the two HTTP-visible endpoints:
  `GET /v1/ws` and `GET /v1/events`.

## Why Redis Pub/Sub instead of Streams or a new broker

Redis was already a first-class, wired dependency with no pub/sub usage
anywhere in the codebase. Streams (`XADD`/`XREAD`) would give at-least-once
delivery semantics this ticket doesn't ask for (dashboard/telemetry
events are acceptable to drop under backpressure — see
[Scaling](./06-scaling.md)); Pub/Sub is simpler, already available, and
matches the "never block ingestion" requirement, since `EventBus.publish()`
never raises and a `PUBLISH` with no active pattern-subscriber is a no-op
rather than a queue backing up.

## Why one process-wide subscription, not one per client

If every connected WebSocket/SSE client opened its own Redis
subscription, connection count would be bounded by browser tabs, not
infrastructure. Instead, each backend replica opens exactly one
`PSUBSCRIBE realtime:org:*` (started once in `ConnectionManager.start()`,
called from `AppContainer.create()`), and fans each received event out to
that replica's own in-memory connection registry. Redis subscription
count scales with replica count, not client count.

## What this EP deliberately does not touch

- The existing polling APIs — unchanged, still the source of truth for
  historical queries.
- The `usage_records` schema — no migration, no new columns.
- The frontend — no new UI. Live dashboard widgets are EP-19.2's scope.
- Auth — no new token type, no new permission. See
  [Authentication](./05-authentication.md).
