# COSTORAH Monitoring Agent — Architecture

## What this is

The COSTORAH Monitoring Agent (`costorah-agent`) is a standalone, independently
distributable Python 3.12 process that polls AI provider APIs for usage/cost
data, normalizes it to a common schema, and delivers it to COSTORAH's Usage
Ingestion API (`POST /v1/ingest/usage`, EP-16) using an Organization API Key
(EP-15). It does not import backend code — the two projects share a schema
contract, not a codebase.

It is designed to run *under* a process supervisor (systemd, Docker,
Kubernetes, a Windows Scheduled Task/Service) rather than as its own daemon.
See `DEPLOYMENT.md`.

## Design goals, in priority order

1. **Never lose telemetry.** A usage event that has been collected must
   eventually reach COSTORAH, even across process restarts, extended
   backend outages, or bursts that exceed in-memory capacity.
2. **Never fabricate data.** If a provider doesn't expose a usage/cost API
   the agent can reach with the credentials it has, the agent says so
   (via `health()`) instead of inventing a plausible-looking number.
3. **Never fail closed on one bad component.** A crashing collector, a
   malformed provider response, or a delivery failure must not stop the
   agent from serving every other provider or endpoint.
4. **Extensible without architectural change.** Adding a new provider, or
   a future framework/SDK integration (LangChain, CrewAI, MCP servers,
   etc.), is "implement `BaseCollector`, register it" — nothing else in
   the agent changes.

## Component overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                              Agent                                   │
│  (agent.py — owns lifecycle, wires everything below together)        │
│                                                                        │
│  ┌────────────────┐   ┌──────────────┐   ┌────────────────────────┐ │
│  │  Collectors     │   │ Event Queue  │   │ Sender                 │ │
│  │  (plugins)      │──▶│ (in-memory)  │──▶│ (drains queue + retry  │ │
│  │  BaseCollector  │   │ overflow to  │   │  store, calls HTTP     │ │
│  │  subclasses     │   │ SQLite ──────┼──▶│  client, reclassifies  │ │
│  └────────────────┘   └──────────────┘   │  failures)             │ │
│         ▲                     ▲          └───────────┬────────────┘ │
│         │                     │                       │              │
│  ┌──────┴──────┐      ┌───────┴────────┐      ┌───────▼───────────┐ │
│  │ Collection   │      │ SQLite Event   │      │  HttpClient        │ │
│  │ Loop         │      │ Store          │      │  (Bearer auth,     │ │
│  │ (interval-   │      │ (durable retry │      │   POST /v1/ingest/ │ │
│  │  driven poll)│      │  queue)        │      │   usage)           │ │
│  └──────────────┘      └────────────────┘      └────────────────────┘│
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Local HTTP server (aiohttp, 127.0.0.1:9091 by default)          │ │
│  │  GET /health    — status, queue depth, collector health          │ │
│  │  GET /metrics   — Prometheus text exposition format               │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## The plugin architecture: `BaseCollector`

Every usage source — a provider REST API today, an OpenAI/Anthropic SDK
instrumentation hook or an MCP server tomorrow — implements the same four
lifecycle methods (`costorah_agent/collectors/base.py`):

```python
class BaseCollector(ABC):
    name: str  # provider slug, matches the EP-16 ingestion catalog

    def __init__(self, config: dict[str, Any]) -> None: ...

    async def collect(self) -> list[NormalizedUsageEvent]:
        """One poll. Return []  for 'nothing new', never raise for that case."""

    def normalize(self, raw: Any) -> NormalizedUsageEvent:
        """Pure function: provider-native record -> common schema.
        No I/O — independently unit-testable against fixture payloads."""

    async def health(self) -> CollectorHealth:
        """Cheap status check. Must not raise."""

    async def shutdown(self) -> None:
        """Release resources (HTTP clients, etc). Default no-op."""
```

`collect()` is expected to call `normalize()` internally, but `normalize()`
is exposed separately so it can be tested with zero network I/O — this is
exactly what `tests/unit/test_collectors.py` does for every built-in
collector.

The agent's core loop (`Agent._collect_once`) never has provider-specific
logic. It only ever calls these four methods on whatever `BaseCollector`
instances the `CollectorRegistry` handed it. Adding OpenAI SDK
instrumentation, a LangChain callback, or an MCP server integration is a new
`BaseCollector` subclass and one `registry.register(...)` call — nothing in
`agent.py`, the queue, the sender, or the transport layer changes.

### `CollectorRegistry`

A name → `BaseCollector`-subclass mapping (`collectors/registry.py`).
`register_builtin_collectors()` registers the six providers shipped with
EP-17. `build_enabled()` builds an instance for every name in
`config.providers` that *has* a registered implementation — an enabled name
with no implementation yet (e.g. `grok`, `cohere`, `bedrock`, `mistral`,
which `config.py` already recognizes as valid provider names) is a silent
forward-compatibility no-op, not a startup failure. This is what lets
`config.example.yaml` list all ten catalog providers today, years before
every collector ships.

### Built-in collectors and their honesty tier

Real usage/cost data isn't uniformly available from every provider with
just an API key. Rather than fabricate numbers for providers that don't
expose one, EP-17 ships three tiers, documented in each collector's own
module docstring:

| Provider | Tier | What it actually does |
|---|---|---|
| **OpenAI** | Real | Polls `GET /v1/organization/usage/completions` with an Admin key. Cost is `0.0` — the Usage API doesn't return cost; the separate Costs API isn't wired up yet. |
| **OpenRouter** | Real | Polls `GET /v1/auth/key` for account-level aggregate spend; emits the *delta* since the last poll (one synthetic event per poll, not per-request — OpenRouter's public API doesn't expose per-request usage without the caller's own generation IDs). |
| **Anthropic** | Real, honest degradation | Polls `GET /v1/organizations/usage_report/messages` with an Admin key. On any HTTP/JSON error, logs a warning and returns `[]` — mirrors the backend's own EP-08 Anthropic adapter precedent of treating usage reporting as an optional capability. |
| **Google (Vertex/Gemini)** | Honest stub | `collect()` always returns `[]`. Real data requires GCP Billing Export to BigQuery — IAM/project setup outside this agent's scope. `health()` says so. |
| **Azure OpenAI** | Honest stub | `collect()` always returns `[]`. Real data requires an Azure AD app registration + Cost Management API access. `health()` says so. |
| **Ollama** | Real connectivity check, no usage API | Ollama has no usage/cost API — local models are free/unmetered. `collect()` always returns `[]`; `health()` does a real `GET /api/tags` to confirm the local daemon is reachable. |

## Data flow: Memory Queue → Retry Queue → HTTP Sender

```
NormalizedUsageEvent
        │  .to_ingestion_payload()
        ▼
   EventQueue.put(event_id, payload)
        │
        ├── queue not full ──▶ held in asyncio.Queue (fast path)
        │
        └── queue full ──▶ overflow directly to SQLiteEventStore
                            (never blocks the collection loop, never drops)

Sender.run_once() [called every min(interval_seconds, 5s)]:
    1. drain up to batch_size items from EventQueue  (attempt=1)
    2. drain up to batch_size *due* retries from SQLiteEventStore
    3. for each: HttpClient.send_usage_event(payload)
         SUCCESS / DUPLICATE   -> remove from durable store, done
         VALIDATION_FAILED     -> log loudly, drop permanently (never retried —
                                   a byte-identical malformed payload can never
                                   succeed, and retrying it forever would grow
                                   the store unboundedly for no benefit)
         AUTH_FAILED / RETRYABLE_ERROR
                                -> persist/update in SQLiteEventStore with
                                   next_retry_at = now + RetryPolicy.delay_for_attempt(n)
```

Backoff schedule (`queue/retry.py`, matches the EP-17 spec exactly):
`1, 2, 4, 8, 16, 30, 60` seconds, then holds at 60s for every attempt after
that. `max_attempts=None` (the default) means retry forever — this is what
"never lose telemetry" requires in practice: an operator fixing a revoked
API key three days later should still see that backlog drain, not find it
silently discarded.

## Sequence diagram: one usage event, end to end

```
Provider API        Collector        EventQueue      SQLiteStore      Sender        HttpClient      COSTORAH API
     │                   │                │               │              │               │                │
     │◀──GET usage───────│                │               │              │               │                │
     │───response───────▶│                │               │              │               │                │
     │                   │─normalize()    │               │              │               │                │
     │                   │  (pure fn)     │               │              │               │                │
     │                   │───put(event)──▶│               │              │               │                │
     │                   │                │  (in memory,  │              │               │                │
     │                   │                │   or overflow │              │              │               │                │
     │                   │                │   to SQLite)──▶              │              │               │                │
     │                   │                │               │              │               │                │
     │                   │                │◀──get_batch────┼──────────────│               │                │
     │                   │                │               │              │───POST /v1/ingest/usage───────▶│
     │                   │                │               │              │   Authorization: Bearer costorah_live_...
     │                   │                │               │              │◀──200 {success, usage_id}──────│
     │                   │                │               │◀─remove()────│               │                │
     │                   │                │               │              │                                │
     │                   │                │               │   [on failure: mark_failed(next_retry_at)]     │
     │                   │                │               │              │                                │
     │                   │                │               │◀──dequeue_due()──(next Sender.run_once() pass, │
     │                   │                │               │                   once next_retry_at elapses)  │
```

## Graceful shutdown

On SIGTERM/SIGINT (`Agent._install_signal_handlers`, falls back cleanly on
Windows where `add_signal_handler` isn't supported for these signals):

1. Cancel the collection and delivery loop tasks.
2. Best-effort final `Sender.run_once()` flush — whatever's already queued
   gets one more delivery attempt before shutdown, so a clean restart
   doesn't need a full retry cycle for data collected seconds earlier.
3. `shutdown()` every collector (closes their HTTP clients).
4. Close the ingestion `HttpClient` and the `SQLiteEventStore`.

Nothing in this path can lose an event that was already durably queued:
worst case, the final flush fails and the event is picked up by the retry
loop on the next process start (the SQLite store is a file, not memory).

## Security posture

See `docs/DEVELOPER_GUIDE.md` and `docs/TROUBLESHOOTING.md` for details;
summary here:

- API key sent once per request as a Bearer `Authorization` header, over
  TLS with certificate verification on by default.
- Structured logging redacts known-sensitive field names and any
  `costorah_live_...` substring embedded in *any* logged value, as a
  belt-and-suspenders guarantee even if a call site passes something it
  shouldn't (`logging_setup.py::redact_sensitive_fields`).
- The local health/metrics HTTP server binds `127.0.0.1` by default, not
  `0.0.0.0` — it exposes operational metadata about a process holding a
  live API key and should not be reachable off-host without an explicit
  opt-in.
- `KeyStore` (`security/key_store.py`) offers Fernet-encrypted at-rest
  storage for the API key with owner-only file permissions on POSIX — an
  honest improvement over plaintext `config.yaml`, but explicitly **not**
  equivalent to an OS-native secret store (Windows DPAPI / macOS Keychain
  / Linux Secret Service). The recommended production posture is still to
  inject the key via the `COSTORAH_AGENT_ORGANIZATION__API_KEY`
  environment variable from your own secret manager.
