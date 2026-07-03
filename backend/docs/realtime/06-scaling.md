# Scaling

## Performance targets from the ticket

| Target | Status |
|---|---|
| 10,000 concurrent connections | Architecturally supported (bounded per-connection memory, no per-client Redis subscription); **not load-tested in this sandbox** — see [Honest limits](#honest-limits-of-this-eps-verification) |
| 100,000 events/minute | Dispatch is O(connections in that org) per event with no I/O in the hot path — see [Dispatch cost](#dispatch-cost) |
| Sub-100ms dispatch latency | `dispatch()` is synchronous, non-blocking, in-memory `Queue.put_nowait()` — no network call, no lock contention beyond a dict lookup |
| No blocking operations | `EventBus.publish()` and `dispatch()` never `await` inside the hot path in a way that can stall on a slow client (see below) |

## How horizontal scaling works

Each backend replica runs exactly one `ConnectionManager`, which opens
exactly one Redis `PSUBSCRIBE realtime:org:*` subscription
(`EventBus.subscribe_all_organizations()`, started once in
`AppContainer.create()` → `connection_manager.start()`). A client
connects to whichever replica its load balancer routes it to; that
replica's `ConnectionManager` only knows about connections registered
locally (`self._connections`, `self._by_org` — in-process dicts). Redis
Pub/Sub fans the same published event out to every replica's
subscription, so a client connected to replica B still receives an event
published from a request handled by replica A. This means:

- Redis subscription count = number of replicas, not number of clients.
- Adding replicas adds connection capacity roughly linearly (each new
  replica can hold its own share of the 10,000-connection target).
- No replica needs to know about another replica's connections — there
  is no cross-replica RPC in the dispatch path.

## Dispatch cost

`ConnectionManager.dispatch(organization_id, event)` iterates
`self._by_org[organization_id]` — typically a small set (the number of
that one organization's currently-open dashboard tabs/SDK connections,
not the whole platform) — and calls `queue.put_nowait(event)` per
connection. This is a dict lookup plus an O(n) loop over that
organization's local connections, with no `await` and no lock. It cannot
stall on a slow consumer: `put_nowait` either succeeds immediately or
raises `QueueFull`, which is caught and turned into a dropped-event
metric, never a blocked dispatch loop.

## Backpressure

Every connection has a bounded `asyncio.Queue(maxsize=256)`
(`DEFAULT_QUEUE_MAXSIZE` in `connection_manager.py`). If a client can't
keep up (a stalled network, a paused browser tab), its queue fills and
further events for *that connection only* are dropped — every other
connection, and the ingestion request that produced the event, is
unaffected. Drops increment `aifinops_realtime_events_dropped_total`
(see [Monitoring](#monitoring)). A client that reconnects can recover
recent history via SSE's `Last-Event-ID` replay
([SSE Guide](./03-sse-guide.md#reconnecting-with-last-event-id)); there
is no equivalent recovery for a live WebSocket connection that dropped
events without disconnecting.

## Monitoring

Real Prometheus metrics (`app/realtime/metrics.py`, `prometheus_client`,
not the hand-written static block the pre-existing `/metrics` endpoint
used to return alone) are appended to `GET /metrics`:

| Metric | Type | Meaning |
|---|---|---|
| `aifinops_realtime_active_connections{kind}` | Gauge | Currently open connections, labeled `websocket`/`sse` |
| `aifinops_realtime_events_dispatched_total` | Counter | Events successfully queued for a connection |
| `aifinops_realtime_events_dropped_total` | Counter | Events dropped due to a full connection queue |
| `aifinops_realtime_reconnects_total{kind}` | Counter | Reconnect attempts (WS `?reconnect=1`, SSE `Last-Event-ID`) |
| `aifinops_realtime_heartbeat_failures_total` | Counter | Heartbeats that went unanswered |
| `aifinops_realtime_dispatch_latency_seconds` | Histogram | (Wired but not yet populated with real timing samples in this EP — see [Honest limits](#honest-limits-of-this-eps-verification)) |

## Honest limits of this EP's verification

This backend runs in a shared, resource-constrained sandbox with no
dedicated load-testing infrastructure. `tests/test_ep19_1.py` proves
correctness (isolation, backpressure-drop behavior, auth, heartbeat
bookkeeping) with a handful of connections, not the literal
10,000-connection / 100,000-events-per-minute scale named in the ticket.
The architecture (bounded queues, no per-client Redis subscription,
O(local connections) dispatch) is what makes that scale plausible on
real infrastructure, but claiming it was measured here would be
dishonest — it was reasoned about and unit-verified at small scale, not
load-tested at the target scale. `dispatch_latency_seconds` is defined
and would need to be recorded around the `dispatch()` call to actually
populate it — it is currently registered but not yet observed anywhere,
which is called out here rather than left silently unfinished.
