"""Real-time telemetry platform foundation — EP-19.1.

Introduces an event-driven layer on top of the existing polling
architecture (SDK -> Usage API -> Queue -> Database -> Dashboard), without
rewriting any of it:

  SDK -> Usage API -> Queue -> Database -> Dashboard (Polling)   [unchanged]
                          |
                          +--> EventBus -> ConnectionManager -> WS / SSE

Reuses, does not reimplement:
  - Authentication: `app.auth.tokens.decode_access_token`,
    `app.services.api_key_auth_service.ApiKeyAuthService` (see `auth.py`)
  - Organizations/RBAC: `app.auth.dependencies.ensure_org_membership`,
    `app.auth.rbac.Permission`/`has_permission`
  - Redis: the shared `AppContainer.redis` client (`app.core.redis`)
  - Database sessions: `AppContainer.session_factory` (short-lived,
    per-operation sessions — see `auth.py`'s docstring for why a
    persistent WebSocket connection can't hold one request-scoped session)

Modules:
  events.py             — `RealtimeEvent` schema + `EventType` enum
  event_bus.py           — Redis Pub/Sub publish/subscribe, per-organization
                            channels, plus a bounded per-org replay buffer
                            for SSE `Last-Event-ID` reconnects
  connection_manager.py  — in-process registry of active WS/SSE connections,
                            organization-scoped dispatch, bounded per-connection
                            queues (backpressure), connection metadata
  auth.py                — WS/SSE-compatible thin wrappers around the
                            existing JWT/API-key validation functions
  rate_limit.py          — per-IP sliding-window limiter for connection
                            attempts (mirrors `app.auth.rate_limit`'s
                            Redis-with-memory-fallback pattern)
  metrics.py              — real Prometheus instrumentation for this
                            feature (active connections, events/sec,
                            dropped events, reconnects, heartbeat
                            failures, dispatch latency)
"""
