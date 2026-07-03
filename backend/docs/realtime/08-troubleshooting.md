# Troubleshooting

## WebSocket connection closes immediately with code 4401

Authentication failed. Check the reason in the close frame's `reason`
field (sent as the WS close reason string, mirroring
`RealtimeAuthErrorReason`):

- `missing_token` — no `Authorization` header and no `?token=` query
  parameter.
- `invalid_token` / `expired_token` — the JWT or API Key itself is bad.
  For a JWT, check it hasn't expired (`decode_access_token` uses the same
  30s leeway and expiry rules as every other authenticated endpoint —
  this is not a real-time-specific expiry policy).
- `missing_organization` — a JWT was used without `?organization_id=`.
  API Keys don't need this (they belong to one organization already).
- `organization_mismatch` — an API Key's own organization doesn't match
  the `?organization_id=` you passed. Either omit the parameter or fix
  it.
- `not_a_member` — the authenticated user exists but isn't a member of
  the requested organization.
- `insufficient_permissions` — the user's role, or the API Key's granted
  scopes, doesn't include `usage:read`.

## WebSocket connection closes with code 4429

Rate limited. `ConnectionRateLimiter` allows 30 connection *attempts* per
IP per 60-second window by default. This is attempts, not concurrent
connections — reconnect loops that retry aggressively on failure will
hit this quickly. Back off between retries.

## WebSocket connection closes with code 4408

Heartbeat timeout — the server sent a ping and got no frame back within
10 seconds. Common causes: the client's event loop is blocked (e.g. by
synchronous work on the same thread), a network path is silently
dropping packets, or a load balancer/proxy is buffering frames in a way
that delays the pong past the client's own send. See
[Deployment](./07-deployment.md#load-balancer--proxy-requirements) for
proxy-side causes.

## SSE endpoint returns 401

Same failure reasons as the WebSocket 4401 case, translated to an HTTP
401 with the reason in the JSON body's `detail` field — check that field
directly (`curl -v` or your HTTP client's error body) rather than
guessing from the status code alone.

## SSE endpoint returns 429

Same rate limiting as WebSocket 4429, translated to an HTTP 429.

## Events aren't arriving even though the connection is open

1. **Wrong organization.** Double-check `?organization_id=` (or the
   API Key's own organization) matches the organization the events are
   actually being published for. Organization isolation is intentional
   and total — there is no cross-organization debug mode.
2. **The event type isn't actually emitted yet.** Only `usage.created` is
   wired up in this EP — see [Event Model](./04-event-model.md#event-types)
   for the full honest list of what's defined-but-not-emitted. If you're
   waiting for a `budget.exceeded` event, it will never arrive; no code
   path emits it.
3. **The connection's queue silently dropped it.** If the client fell
   behind (didn't read fast enough), events for that connection were
   dropped under backpressure. Check
   `aifinops_realtime_events_dropped_total` on `/metrics` — if it's
   increasing, the client-side consumer loop needs to be faster, not the
   server. For SSE, a reconnect with `Last-Event-ID` can recover up to an
   hour of history; a live WebSocket cannot.
4. **`usage.created` specifically: is `is_duplicate` true?** A repeated
   `request_id` for the same organization is treated as an idempotent
   replay by `UsageIngestionService` and does **not** publish a new
   event — this matches the ticket's requirement that a duplicate ingest
   isn't an error, but it also means it isn't a new real-time event.

## `GET /metrics` doesn't show real-time metrics

Confirm `prometheus-client` is actually installed
(`pip show prometheus-client` inside the backend's virtualenv) — it was
added as a new dependency in this EP
(`backend/pyproject.toml`). If it's missing, `app/realtime/metrics.py`
fails to import and the application won't start at all (it's imported
eagerly by `app/core/container.py`), so a missing dependency shows up as
a startup failure, not a silently-empty `/metrics` response.

## Redis is unreachable

`EventBus.publish()` and `EventBus.replay_since()` degrade
gracefully — they log a warning and return (publish) or an empty list
(replay) rather than raising, so a Redis outage does not fail the usage
ingestion request that triggered a publish, and does not crash an
in-progress WebSocket/SSE connection. It does mean no real-time events
are delivered during the outage; the existing polling APIs are
unaffected since they don't depend on Redis Pub/Sub at all. New
connection *attempts* still require Redis reachability indirectly (the
container itself requires a working Redis client at startup, per
existing pre-EP-19.1 behavior), but an already-open connection survives
a transient Redis blip without disconnecting.
