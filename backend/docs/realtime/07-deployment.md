# Deployment

## New dependency

`prometheus-client>=0.21.0` was added to `backend/pyproject.toml`'s main
dependency list (needed at runtime by `app/realtime/metrics.py`, not just
for tests). No other new runtime dependencies — `websockets` (used by the
Python example clients and the WS integration tests) was already present
transitively via `fastapi[standard]`/`uvicorn[standard]`, and the server
side of the WebSocket gateway uses Starlette/FastAPI's built-in
`WebSocket` support, not the `websockets` package directly.

## Configuration

No new environment variables or settings fields were added. The
real-time layer reuses:

- `REDIS_URL` / `redis_url` (`app.config.settings.Settings`) — the same
  Redis instance the existing `LoginRateLimiter` and session cache use.
- `JWT_SECRET`, `JWT_ALGORITHM` — unchanged, reused by
  `decode_access_token()`.
- `DATABASE_URL` — unchanged; `authenticate_realtime_connection()` opens
  short-lived sessions from the same `session_factory` every other
  request-scoped dependency uses.

## Process model

`ConnectionManager.start()` is called once per process, from
`AppContainer.create()` (`backend/app/core/container.py`), which runs in
FastAPI's `lifespan()`. Running multiple Uvicorn/Gunicorn worker
processes (or multiple container replicas) is safe and expected — each
process gets its own `ConnectionManager` and its own
`PSUBSCRIBE realtime:org:*` subscription; Redis fans events out to all of
them. `ConnectionManager.stop()` is called from `AppContainer.close()`
on graceful shutdown, cancelling the dispatch loop task.

## Load balancer / proxy requirements

- **WebSocket upgrade** must be passed through (`Connection: Upgrade`,
  `Upgrade: websocket`). Any standard reverse proxy in front of Uvicorn
  (nginx, an ALB with WS support enabled, etc.) needs this configured —
  no different from any other FastAPI WebSocket route.
- **SSE responses must not be buffered.** The SSE endpoint sets
  `X-Accel-Buffering: no` (nginx's convention to disable proxy buffering
  for that response) and `Cache-Control: no-cache`. A proxy that buffers
  the response body will defeat the point of SSE — events would arrive
  in bursts instead of as they're published.
- **Idle timeouts** on the SSE response should exceed 30s (the heartbeat
  interval that keeps the connection alive) with margin — a proxy with a
  15s idle timeout will kill SSE connections between heartbeats.

## Rollout safety

This EP is purely additive at the API surface: two new routes
(`GET /v1/ws`, `GET /v1/events`), one new field-free append to an
existing endpoint's response headers (`GET /metrics`'s payload gains
extra lines, existing lines are untouched), and one new `event_bus.publish()`
call inside `POST /v1/ingest/usage` that is fire-and-forget and never
raises (`EventBus.publish()` catches and logs, never propagates). A
deployment of this EP cannot break any existing endpoint's response
shape or status codes. If `AppContainer.create()`'s new
`ConnectionManager`/`EventBus`/`ConnectionRateLimiter` construction ever
failed, it would fail application startup the same way a Redis/Postgres
connectivity failure already does — this EP does not add a new startup
failure mode beyond "the container already requires Redis to be
reachable," which was already true before this EP.
