# Performance (EP-18.4, EP-18.5)

Numbers below were gathered by actually running each SDK, not estimated.
Both SDKs are built around the same principle established in EP-18.3:
`track()` only enqueues an event in memory and returns — it never blocks
on a network call — so its cost is dominated by object construction and
queue insertion, not I/O.

## Python

Measured with `sdk/python/costorah`, a `Costorah` client backed by an
`httpx.MockTransport` that returns instantly (isolating SDK overhead from
real network latency), `queue_size=200_000`, after a 20-call warm-up:

| Metric | Result |
|---|---|
| Average `track()` latency (500 samples) | **0.0155 ms** |
| 100,000 `track()` calls — total time | **1.98 s** |
| 100,000 `track()` calls — average per call | **0.0198 ms** |
| Memory delta for 100,000 queued events | **53.9 MB** (~0.55 KB/event) |

Reproducible via the same pattern used in
`sdk/python/tests/test_cli.py`'s and the instrumentor test suites' use of
`httpx.MockTransport` — construct a `Costorah` client with a
zero-latency mock transport, then time `track()` in a loop.

## JavaScript

Enforced continuously in CI via `sdk/javascript/tests/reliability/healthAndClient.test.ts`
and `sdk/javascript/tests/instrumentation/performance.test.ts` (both run
on every push/PR by the `sdk-javascript` CI job):

| Metric | Result |
|---|---|
| Average `track()` latency (200 samples) | asserted **< 1 ms** |
| 100,000 queued events — total time | asserted **< 10 s** |
| Memory delta for 100,000 queued events | asserted **< 150 MB** |

The JS thresholds are intentionally looser than the Python figures above
because they're CI assertions meant to catch regressions across widely
varying CI runner hardware, not tight benchmarks — the actual numbers on
typical hardware run well under these bounds.

## Cross-language comparison

Both SDKs achieve the same qualitative result: `track()` is a
sub-millisecond, non-blocking, in-memory operation regardless of
language, and 100,000 events can be queued in low single-digit seconds
with a memory footprint in the tens of MB. Neither SDK's instrumentation
or reliability layer (queue → worker → retry → circuit breaker →
connection pool) is a bottleneck at this scale — cost is dominated by
per-event object allocation.

## Python framework middleware overhead (EP-18.5)

EP-18.4 flagged framework middleware overhead as not separately
load-tested; EP-18.5 measured it directly for the Python integrations
it added, using the same methodology (a `Costorah` client backed by a
zero-latency `httpx.MockTransport`, isolating middleware/SDK overhead
from real network latency), against a **target of <1 ms overhead and
<20 MB memory** stated in the EP-18.5 ticket:

| Integration | Measurement | Result | Target |
|---|---|---|---|
| Flask (`CostorahExtension`) | avg per-request overhead, 500 samples, full `test_client()` round trip | **0.28 ms** | <1 ms ✓ |
| Django (`CostorahMiddleware`) | avg per-call overhead, 500 samples, direct middleware invocation | **0.008 ms** | <1 ms ✓ |
| Celery (`CostorahCelery`) | avg per-task signal overhead, 500 samples, `task.apply()` | **0.085 ms** | <1 ms ✓ |
| Flask (`CostorahExtension`) | memory delta, 10,000 requests | **~0 MB** (no measurable RSS growth after warm-up) | <20 MB ✓ |

The Flask number includes full Flask request dispatch (URL routing,
view invocation) on top of the middleware itself, not just the
middleware in isolation — the true `CostorahWSGIMiddleware`/
`CostorahExtension` contribution is smaller than 0.28 ms. The Django
number isolates the middleware call directly (via `RequestFactory` +
calling the middleware object itself), which is why it reads
lower — both are consistent with the underlying mechanism
(`contextvars.ContextVar` set/reset) being sub-microsecond; the
measured numbers are dominated by each framework's own request-object
construction, not by anything this SDK adds.

ASGI/WSGI generic middleware and Starlette (a re-export of the FastAPI
middleware, already measured qualitatively in EP-18.4) were not
separately benchmarked — they share the identical code path as
Flask/FastAPI's middleware (Flask literally wraps
`CostorahWSGIMiddleware`), so the Flask/FastAPI numbers above are
representative.

## What this doesn't cover

- **Sustained network throughput** to a real (non-mocked) COSTORAH
  ingest endpoint — the numbers above isolate SDK-side overhead, not
  end-to-end delivery latency.
- **Concurrent-load behavior** of the framework middleware (many
  simultaneous requests/tasks) — the measurements above are sequential,
  single-threaded per-call overhead, not a concurrency/throughput
  benchmark.
- **Cold-start impact** on serverless targets (AWS Lambda, Cloudflare
  Workers) — not applicable in these EPs since those integrations are
  not yet built (see `FRAMEWORK_INTEGRATIONS.md`).
- **JavaScript framework middleware overhead** beyond Express (already
  covered qualitatively in EP-18.4) — out of scope for EP-18.5, which
  was Python-only.
