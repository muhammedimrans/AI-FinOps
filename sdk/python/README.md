# costorah (Python)

Official Python SDK for [COSTORAH](https://costorah.com) — report AI
usage/cost telemetry in a few lines of code.

```bash
pip install costorah
```

```python
from costorah import Costorah

client = Costorah(api_key="costorah_live_xxxxxxxxx")

client.track(
    provider="openai",
    model="gpt-4.1",
    input_tokens=500,
    output_tokens=220,
    cost=0.041,
    latency_ms=621,
)
```

That's it — the event is validated immediately (raising a
`costorah.ValidationError` right away if it's malformed) and handed to a
background reliability pipeline that authenticates (EP-15) and delivers
it to COSTORAH's Usage Ingestion API (EP-16) — queued, retried, and
circuit-broken automatically. `track()` itself never blocks on the
network; see [Reliability](../docs/RELIABILITY.md) for the full pipeline.

## Configuration

```python
client = Costorah(
    api_key="costorah_live_xxxxxxxxx",
    endpoint="https://api.costorah.com",  # default
    timeout=30,             # seconds, per HTTP request
    verify_tls=True,        # disable ONLY for local dev against a self-signed backend
    batch_size=25,          # events delivered concurrently per background pass
    queue_size=10_000,      # in-memory queue capacity
    overflow_policy="drop_oldest",  # "drop_newest" | "drop_oldest" | "block"
    persistent_queue=False, # True: survive a process crash/restart (SQLite)
    compression=True,       # gzip large payloads
    retry=True,             # retry transient failures with backoff
)
```

See [`RELIABILITY.md`](../docs/RELIABILITY.md) for what each of these
does in the pipeline.

Prefer supplying the API key from an environment variable rather than
hardcoding it:

```python
import os
from costorah import Costorah

client = Costorah(api_key=os.environ["COSTORAH_API_KEY"])
```

## Manual tracking

```python
result = client.track(
    provider="anthropic",       # one of the COSTORAH provider catalog — see below
    model="claude-sonnet-4",
    input_tokens=200,
    output_tokens=80,
    cost=0.012,
    latency_ms=410,
    status="success",           # "success" | "error" | "timeout" | "cancelled"
    metadata={"endpoint": "/chat"},
)

print(result.queued)  # True — accepted into the pipeline; delivery is async
```

`result.usage_id`/`result.processed_at`/`result.duplicate` are `None`/
`False` here — they're only known once the event is actually delivered,
which happens in the background. Call `client.flush()` first if you need
to observe them (or just check `client.queue_stats()` afterward).

Supported `provider` values: `openai`, `anthropic`, `grok`, `google`,
`azure_openai`, `openrouter`, `ollama`, `cohere`, `bedrock`, `mistral`.

Reusing the same `request_id` across calls is safe — COSTORAH treats it as
an idempotency key and returns the original record with `duplicate=True`
instead of double-counting. If you don't supply one, the SDK generates a
random one per call.

## Error handling

`track()` only raises synchronously for problems it can detect locally,
before anything is queued:

```python
from costorah import ValidationError

try:
    client.track(provider="not-a-real-provider", model="gpt-4.1", cost=0.01)
except ValidationError:
    # unsupported provider, negative tokens, blank model, etc. — caught
    # before the event ever enters the pipeline
    ...
```

`AuthenticationError`, `RateLimitError`, `ServerError`, and
`NetworkError` are never raised from `track()` anymore — those are all
delivery-time failures, and delivery happens asynchronously in the
background (see [Reliability](../docs/RELIABILITY.md)). They're
retried automatically and, if a failure is ultimately permanent
(`AuthenticationError`-equivalent, i.e. a 401/403), the event is dropped
and logged rather than raised — telemetry can never break your
application's request path.

## Retry behavior

Transient delivery failures are retried automatically with exponential
backoff — `1, 2, 4, 8, 16, 30, 60, 120, 300` seconds, holding at 300s —
**indefinitely**, not up to a bounded attempt count, because delivery no
longer blocks any caller. A circuit breaker stops sending (without
losing queued events) after repeated failures and probes periodically to
recover. Permanent failures (400/401/403/404) are dropped immediately —
resending an unchanged bad request or an invalid key can't succeed. See
[`RELIABILITY.md`](../docs/RELIABILITY.md) for the full retry/circuit
breaker/persistence design.

## Thread safety

A single `Costorah` instance is safe to share across threads. Each
`track()` call only touches the thread-safe in-memory queue; delivery
happens on a single dedicated background thread (its own asyncio event
loop, driving a shared `httpx.AsyncClient` connection pool) regardless of
how many threads call `track()` concurrently.

## Logging

The SDK logs retry attempts via the standard `logging` module under the
`costorah` logger hierarchy, with a redaction filter that strips API keys
and other sensitive values from every log line — even accidentally.
Configure verbosity the normal way:

```python
import logging
logging.getLogger("costorah").setLevel(logging.DEBUG)
```

## Automatic instrumentation

Skip manual `track()` calls entirely for supported providers:

```python
from openai import OpenAI
from costorah.instrumentation import OpenAIInstrumentor

OpenAIInstrumentor().instrument()
client = OpenAI()
client.chat.completions.create(model="gpt-4o", messages=[...])  # tracked automatically
```

Supports OpenAI, Azure OpenAI, OpenRouter, Ollama, Grok, Anthropic,
Mistral, Amazon Bedrock, Google Gemini, and Cohere — see
`../docs/AUTOMATIC_INSTRUMENTATION.md` for the full guide, including
streaming, cost calculation, and privacy guarantees.

## Reliability

Queueing, crash-durable persistence, retry, circuit breaking, and
compression are automatic and always on — no configuration required.

```python
client.flush(timeout=10.0)     # -> bool: wait for pending events to deliver
client.shutdown(timeout=10.0)  # flush, then stop the background worker
client.health()                # {"worker": "running", "queue_depth": 0, ...}
client.queue_stats()           # queue depth, dropped events, retry count, ...
```

See [`RELIABILITY.md`](../docs/RELIABILITY.md) for the full architecture,
delivery guarantee, and configuration reference.

## What's not in this release

Framework-specific plugins and a real multi-event batch ingestion
endpoint (EP-16 currently accepts one event per request — see
`RELIABILITY.md`'s Batch Upload section) are staged for EP-18.4 — see
`../docs/ROADMAP.md`.

## Requirements

Python 3.9+. Single runtime dependency: `httpx`.
