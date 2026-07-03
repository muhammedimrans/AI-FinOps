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

That's it — the event is authenticated (EP-15), validated, and pushed to
COSTORAH's Usage Ingestion API (EP-16) synchronously, raising a
`costorah.*` exception if anything goes wrong instead of failing silently.

## Configuration

```python
client = Costorah(
    api_key="costorah_live_xxxxxxxxx",
    endpoint="https://api.costorah.com",  # default
    timeout=30,          # seconds, per HTTP request
    max_retries=3,       # bounded retry for track() — see "Retry behavior" below
    verify_tls=True,     # disable ONLY for local dev against a self-signed backend
)
```

`batch_size` and `flush_interval` are accepted for forward compatibility
with EP-18.3 (background batching) but have no effect yet — every
`track()` call in this release makes its own HTTP request immediately.

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

print(result.usage_id, result.duplicate)
```

Supported `provider` values: `openai`, `anthropic`, `grok`, `google`,
`azure_openai`, `openrouter`, `ollama`, `cohere`, `bedrock`, `mistral`.

Reusing the same `request_id` across calls is safe — COSTORAH treats it as
an idempotency key and returns the original record with `duplicate=True`
instead of double-counting. If you don't supply one, the SDK generates a
random one per call.

## Error handling

```python
from costorah import (
    AuthenticationError,
    ValidationError,
    RateLimitError,
    ServerError,
    NetworkError,
)

try:
    client.track(provider="openai", model="gpt-4.1", cost=0.01)
except AuthenticationError:
    # invalid/expired API key, or the key lacks usage:write — not retried
    ...
except ValidationError:
    # the payload itself was rejected — not retried
    ...
except (RateLimitError, ServerError, NetworkError):
    # already retried internally up to max_retries; still failed
    ...
```

Client-side validation (unsupported provider, negative tokens, etc.) also
raises `ValidationError`, saving a round trip for errors the SDK can catch
locally.

## Retry behavior

Transient failures (`RateLimitError`, `ServerError`, `NetworkError`) are
retried automatically with exponential backoff — `1, 2, 4, 8, 16, 30, 60`
seconds, honoring a `Retry-After` header when the server sends one — up to
`max_retries` (default 3) before the exception is raised to your code.
`AuthenticationError` and `ValidationError` are never retried, since
resending an unchanged bad request or an invalid key can't succeed.

This is a bounded, synchronous retry appropriate for a blocking call in
your request path. A non-blocking background queue with unlimited retry
and offline persistence — conceptually similar to the
[Monitoring Agent](../../monitoring-agent)'s design — is planned for
EP-18.3.

## Thread safety

A single `Costorah` instance is safe to share across threads. Each
`track()` call is independent; the underlying HTTP connection pool
(`httpx.Client`) manages concurrent requests safely.

## Logging

The SDK logs retry attempts via the standard `logging` module under the
`costorah` logger hierarchy, with a redaction filter that strips API keys
and other sensitive values from every log line — even accidentally.
Configure verbosity the normal way:

```python
import logging
logging.getLogger("costorah").setLevel(logging.DEBUG)
```

## What's not in this release

Automatic provider-response detection (`client.track_openai(response=...)`),
auto-instrumentation, background batching/queueing, and framework
integrations are staged for later phases (EP-18.2–EP-18.4) — see
`../docs/ROADMAP.md`. This release covers manual `track()`, which is fully
production-ready on its own.

## Requirements

Python 3.9+. Single runtime dependency: `httpx`.
