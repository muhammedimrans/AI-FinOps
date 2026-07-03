# Enterprise Reliability Layer (EP-18.3)

Telemetry delivery survives poor networks, high throughput, intermittent
failures, process restarts, and provider outages — without ever slowing
down the application's normal execution. `track()` (manual or via
[automatic instrumentation](AUTOMATIC_INSTRUMENTATION.md)) validates its
arguments and returns immediately; delivery happens entirely off the
critical path.

```
Application
  -> Instrumentation / manual track()
  -> Memory Queue          (in-process buffer, track() writes here)
  -> Background Worker     (drains the queue off the critical path)
  -> Persistent Queue      (crash-durable checkpoint, optional)
  -> Compression           (gzip, large payloads only)
  -> Retry Engine          (exponential backoff, forever)
  -> Circuit Breaker       (stops sending during a sustained outage)
  -> Connection Pool       (reused HTTP connection)
  -> Usage API             (EP-16 ingestion)
```

## Quick start

```python
client = Costorah(
    api_key="costorah_live_...",
    batch_size=100,
    persistent_queue=True,
)
```

```typescript
const client = new Costorah({
  apiKey: "costorah_live_...",
  batchSize: 100,
  persistentQueue: true,
});
```

Nothing else changes — `client.track(...)` (and every instrumentor built
on EP-18.2) works exactly as before, just without blocking on the
network.

## What changed about `track()`

Before EP-18.3, `track()` made one blocking HTTP call and returned the
server's actual response (`usage_id`, `processed_at`, `duplicate`).
Blocking is exactly what an "enterprise reliability layer" cannot do —
the whole point is that the caller's request path is never at the mercy
of COSTORAH's own availability. So `track()` now:

1. Validates arguments synchronously (same validation as before — an
   invalid provider/model/token count still raises/rejects immediately).
2. Pushes the built payload into the in-memory queue (O(1)).
3. Returns immediately — well under 1ms, verified in the performance
   tests.

Because delivery happens later, in the background, `TrackResult` can no
longer carry the server's response synchronously:

| Field | Before EP-18.3 | Since EP-18.3 |
|---|---|---|
| `success`/`queued` | delivery succeeded | validated + queued |
| `usage_id`/`processed_at` | from the server | `None`/`undefined` |
| `duplicate` | from the server | always `false` |

Use `client.flush()` when a caller genuinely needs to wait for delivery
(tests, or right before process exit) — see below.

## Queue Architecture

**Memory Queue** — the fast path `track()` writes into. Configurable
`queue_size`/`queueSize` (default 10,000) and `overflow_policy`/
`overflowPolicy`:

- `drop_oldest` (default) — evicts the oldest queued event to make room;
  favors recent telemetry over old telemetry under sustained overflow.
- `drop_newest` — rejects the incoming event, keeping what's already
  queued.
- `block` — waits for room (bounded; Python blocks the calling thread up
  to `block_timeout`, JavaScript awaits without freezing the event loop)
  before falling back to a drop.

**Persistent Queue** — the crash-durability checkpoint. The Background
Worker drains the Memory Queue into it on every pass, before attempting
delivery, so an event only needs to survive as long as it takes to reach
this checkpoint (bounded by the poll interval, well under a second) to
be crash-safe.

- **Python**: SQLite (WAL mode), reusing the same schema/replay shape as
  the Monitoring Agent's (EP-17) offline store. `persistent_queue=False`
  (default) uses an in-memory SQLite database (`:memory:`) — identical
  mechanics, just not durable across a restart. `persistent_queue=True`
  uses a real file, namespaced by a hash of the API key under the
  system temp directory, so the same key on the same machine reuses the
  same file across restarts (what actually makes crash recovery
  possible).
- **JavaScript**: the ticket suggests "LevelDB or equivalent lightweight
  embedded storage." This SDK ships with **zero runtime dependencies**
  (see each README's Requirements section) — adding LevelDB would break
  that guarantee for every consumer, not just those who opt into
  `persistentQueue: true`. Instead, `persistentQueue: true` uses a plain
  newline-delimited-JSON append log via Node's built-in `fs/promises`,
  with an in-memory `Map` as the fast path and periodic compaction so the
  log file doesn't grow unboundedly — the same durability property
  (crash-safe, replay-on-restart), without a binary dependency.
  `persistentQueue: false` (default) skips file I/O entirely.

## Batch Upload — an explicit, honest limitation

The ticket asks for real HTTP batching ("100 events -> 4 batches -> 4
HTTP calls"). EP-16's `POST /v1/ingest/usage` ingestion endpoint accepts
**exactly one usage record per request** — there is no multi-event batch
endpoint, and adding one would mean modifying a previous Engineering
Package's API surface, which this ticket says not to do unless
absolutely necessary.

"Batching" here means what's honestly achievable without that: the
Background Worker groups up to `batch_size`/`batchSize` due events per
pass and delivers them **concurrently** over the pooled connection
(bounded by a concurrency limit), instead of one blocking round trip at
a time. This is a real throughput improvement over naive serial delivery
— but it is still one HTTP request per event, not fewer HTTP requests
than events. A true batch endpoint is a backend (EP-16) change, out of
scope here.

## Retry Strategy

Default exponential backoff schedule (seconds), per the ticket exactly:

```
1, 2, 4, 8, 16, 30, 60, 120, 300
```

held at 300s for all further attempts — retries continue indefinitely
(no max-attempt cutoff) for transient failures, matching the delivery
guarantee below. Retried: `408, 429, 500, 502, 503, 504`, and network
errors with no HTTP status at all. **Never** retried: `400, 401, 403,
404` — an unchanged payload retried against a permanent client error can
never succeed, so these are dropped immediately (logged, and reflected
in `queue_stats()`'s `failed_total`/`failedTotal`). Set `retry=False`/
`retry: false` to drop on the first transient failure instead of
retrying at all.

## Circuit Breaker

Standard three-state design:

- **Closed** — requests flow normally.
- **Open** — after `failure_threshold` (default 5) consecutive delivery
  failures, the breaker opens: no more delivery attempts are made
  (events keep accumulating in the persistent queue) until
  `recovery_timeout` (default 30s) elapses.
- **Half-Open** — after the recovery timeout, a bounded number of probe
  requests (`half_open_max_calls`, default 1) are allowed through. A
  successful probe closes the circuit; a failed probe reopens it
  immediately.

This is genuinely new — EP-17's Monitoring Agent has no circuit-breaker
concept to reuse (confirmed: no such logic exists anywhere in that
package); this is time-based-retry-per-event only. The circuit breaker
adds the missing "stop hammering a downed backend" behavior on top.

## Compression

Payloads at or above 1024 bytes (configurable) are gzip-compressed
before upload, with `Content-Encoding: gzip` set accordingly. Payloads
below the threshold are sent uncompressed — gzip's own framing overhead
can make a tiny payload *larger*, so compressing everything
unconditionally would be counter-productive. A single usage event's JSON
is typically well under 1KB unless its `metadata` is large, so
compression triggers mainly for events with substantial custom metadata.

## Delivery Guarantee

**At-least-once.** COSTORAH will receive every event that:
1. Was successfully queued (not dropped by an overflow policy), and
2. Did not receive a permanent (4xx) rejection.

**Never exactly-once** — a retried event could theoretically be received
more than once by the backend if a prior attempt's response was lost
after the server had already processed it. EP-16's ingestion API is
already idempotent on `request_id` for exactly this reason (a duplicate
`request_id` returns the original record with `duplicate: true` rather
than creating a second one) — the reliability layer's retries are safe
to replay because of that existing EP-16 guarantee, not because this
layer invents its own deduplication.

Events genuinely lost only in documented overflow scenarios: an overflow
policy actively evicting/rejecting events, or an ungraceful process
kill between an event entering the Memory Queue and the next Background
Worker pass persisting it (a window bounded by the poll interval, and
eliminated entirely by calling `flush()`/`shutdown()` before exit).

## Performance

| Target | Measured |
|---|---|
| `track()` latency | <1ms (tests assert this directly) |
| Memory, 100k queued events | <100MB (Python: `resource.getrusage`; JS: heap delta) |
| 100,000 queued events | handled without blocking the caller |

## Security & Privacy

Never persisted: API keys, prompt text, completion text, PII. Only usage
metadata (provider, model, token counts, cost, latency, status, request
ID, timestamp, caller-supplied non-content metadata) ever enters the
queue — the exact same payload shape `track()` already builds and posts
today; the reliability layer adds durability and retry around that
payload, it does not change what's captured. Structured logging follows
the SDKs' existing redaction rules (never logs API keys or secrets).

## SDK Health API

```python
client.health()
# {"worker": "running", "queue_depth": 24, "retry_queue": 3,
#  "circuit": "closed", "compression": "enabled"}

client.queue_stats()
# queue depth, dropped events, retry queue size, worker status,
# sent/failed totals, retry count, avg upload latency, compression
# ratio, last batch size, worker uptime
```

```typescript
client.health();
// same shape (snake_case keys, matching the ticket exactly)

client.queueStats();
// camelCase equivalent of queue_stats()
```

## Public API

```python
client.flush(timeout=10.0)   # -> bool: True if fully drained before the timeout
client.shutdown(timeout=10.0)  # flush, then stop the background worker
client.health()              # -> dict, ticket's literal shape
client.queue_stats()         # -> dict
```

```typescript
await client.flush(10_000);    // -> boolean
await client.shutdown(10_000); // flush, then stop the background worker
client.health();               // -> HealthSnapshot
client.queueStats();           // -> QueueStatsSnapshot
```

`close()` (Python) / no separate `close()` (JavaScript, `shutdown()` is
canonical) remain available as an alias for `shutdown()`.

## Configuration reference

| Key (Python / JS) | Default | Meaning |
|---|---|---|
| `batch_size` / `batchSize` | 25 | events per delivery pass |
| `flush_interval` / `flushInterval` | 5s | caps the worker's idle poll interval |
| `queue_size` / `queueSize` | 10,000 | Memory Queue capacity |
| `overflow_policy` / `overflowPolicy` | `drop_oldest` | `drop_newest` \| `drop_oldest` \| `block` |
| `persistent_queue` / `persistentQueue` | `False`/`false` | crash-durable queue file |
| `compression` / `compression` | `True`/`true` | gzip above the size threshold |
| `retry` / `retry` | `True`/`true` | retry transient failures |

## Migration guide

No code changes required to keep using `track()` — it has the same
signature and still validates the same way. The only behavioral change
is `TrackResult` no longer carrying the server's response synchronously
(see the table above). If your code inspected `result.usage_id` /
`result.processedAt` / `result.duplicate` after `track()`, switch to
`await client.flush()` (or `client.flush()` in Python) before reading
delivery-dependent state, or read `client.queue_stats()` after a flush.

## FAQ

**Does this replace EP-18.2's automatic instrumentation?** No —
instrumentation still normalizes provider responses into usage events;
this layer is what actually delivers them now.

**What happens if I never call `flush()`/`shutdown()`?** Events are
still delivered — the background worker runs continuously as long as
the process is alive. `flush()`/`shutdown()` exist for when a caller
needs a guarantee that delivery has actually happened before doing
something else (exiting the process, asserting in a test).

**Does `persistent_queue=True`/`persistentQueue: true` guarantee
zero data loss?** No — see [Delivery Guarantee](#delivery-guarantee)
above. It significantly narrows the loss window (a crash after the
Memory Queue -> Persistent Queue handoff no longer loses anything), but
it is still at-least-once, not a distributed-transaction guarantee.

**Can I disable all of this and go back to purely synchronous
delivery?** Not in this release — the ticket's success criterion is
that this behavior is automatic and requires no developer action. If you
need delivery confirmation for a specific call, `await client.flush()`
right after `track()` gives you that without reverting the architecture.
