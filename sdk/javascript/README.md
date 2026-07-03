# @costorah/sdk (JavaScript / TypeScript)

Official JavaScript/TypeScript SDK for [COSTORAH](https://costorah.com) —
report AI usage/cost telemetry in a few lines of code.

```bash
npm install @costorah/sdk
```

```ts
import { Costorah } from "@costorah/sdk";

const costorah = new Costorah({
  apiKey: process.env.COSTORAH_API_KEY!,
});

await costorah.track({
  provider: "anthropic",
  model: "claude-sonnet-4",
  inputTokens: 200,
  outputTokens: 80,
  cost: 0.012,
  latencyMs: 410,
});
```

That's it — the event is validated immediately (rejecting right away
with a `ValidationError` if it's malformed) and handed to a background
reliability pipeline that authenticates (EP-15) and delivers it to
COSTORAH's Usage Ingestion API (EP-16) — queued, retried, and
circuit-broken automatically. `track()` itself never blocks on the
network; see [Reliability](../docs/RELIABILITY.md) for the full pipeline.

Ships as both ESM and CommonJS with bundled `.d.ts` types — works from
`import` or `require()`, Node 18+.

## Configuration

```ts
const client = new Costorah({
  apiKey: "costorah_live_xxxxxxxxx",
  endpoint: "https://api.costorah.com", // default
  timeout: 30,     // seconds, per HTTP request
  verifyTls: true,
  batchSize: 25,             // events delivered concurrently per background pass
  queueSize: 10_000,         // in-memory queue capacity
  overflowPolicy: "drop_oldest", // "drop_newest" | "drop_oldest" | "block"
  persistentQueue: false,    // true: survive a process crash/restart
  compression: true,         // gzip large payloads
  retry: true,               // retry transient failures with backoff
});
```

See [`RELIABILITY.md`](../docs/RELIABILITY.md) for what each of these
does in the pipeline.

## Manual tracking

```ts
const result = await client.track({
  provider: "openai", // one of the COSTORAH provider catalog — see below
  model: "gpt-4.1",
  inputTokens: 500,
  outputTokens: 220,
  cost: 0.041,
  latencyMs: 621,
  status: "success", // "success" | "error" | "timeout" | "cancelled"
  metadata: { endpoint: "/chat" },
});

console.log(result.queued); // true — accepted into the pipeline; delivery is async
```

`result.usageId`/`result.processedAt`/`result.duplicate` are
`undefined`/`false` here — they're only known once the event is actually
delivered, which happens in the background. Call `await client.flush()`
first if you need to observe them (or just check `client.queueStats()`
afterward).

Supported `provider` values: `openai`, `anthropic`, `grok`, `google`,
`azure_openai`, `openrouter`, `ollama`, `cohere`, `bedrock`, `mistral`.

Reusing the same `requestId` across calls is safe — COSTORAH treats it as
an idempotency key and returns the original record with `duplicate: true`
instead of double-counting. If you don't supply one, the SDK generates a
random one per call.

## Error handling

`track()` only throws synchronously for problems it can detect locally,
before anything is queued:

```ts
import { ValidationError } from "@costorah/sdk";

try {
  await client.track({ provider: "not-a-real-provider", model: "gpt-4.1", cost: 0.01 });
} catch (err) {
  if (err instanceof ValidationError) {
    // unsupported provider, negative tokens, blank model, etc. — caught
    // before the event ever enters the pipeline
  }
}
```

`AuthenticationError`, `RateLimitError`, `ServerError`, and
`NetworkError` are never thrown from `track()` anymore — those are all
delivery-time failures, and delivery happens asynchronously in the
background (see [Reliability](../docs/RELIABILITY.md)). They're
retried automatically and, if a failure is ultimately permanent
(an `AuthenticationError`-equivalent, i.e. a 401/403), the event is
dropped and logged rather than thrown — telemetry can never break your
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

## Concurrency

Safe for concurrent async operations: a single `Costorah` instance can be
`await`ed from many places at once (e.g. many in-flight request handlers
in the same Node process). Each `track()` call only touches the queue —
delivery is handled by a single background worker loop shared across all
of them.

## Logging

The SDK logs retry attempts through a small built-in console logger with
redaction baked in (API keys and other sensitive values are stripped from
every log line, even accidentally). Supply your own logger — e.g. to
route into pino or winston — via the SDK's internal logger hook if you
need structured log aggregation; see `src/logging.ts`'s `Logger`
interface.

## Automatic instrumentation

Skip manual `track()` calls entirely for supported providers:

```typescript
import OpenAI from "openai";
import { OpenAIInstrumentor } from "@costorah/sdk";

new OpenAIInstrumentor().instrument();
const client = new OpenAI();
await client.chat.completions.create({ model: "gpt-4o", messages: [] }); // tracked automatically
```

Supports OpenAI, Azure OpenAI, OpenRouter, Ollama, Grok, Anthropic,
Mistral, Amazon Bedrock, Google Gemini, and Cohere — see
`../docs/AUTOMATIC_INSTRUMENTATION.md` for the full guide, including
streaming, cost calculation, and privacy guarantees.

## Reliability

Queueing, crash-durable persistence, retry, circuit breaking, and
compression are automatic and always on — no configuration required.

```ts
await client.flush(10_000);    // wait for pending events to deliver
await client.shutdown(10_000); // flush, then stop the background worker
client.health();               // { worker: "running", queue_depth: 0, ... }
client.queueStats();           // queue depth, dropped events, retry count, ...
```

See [`RELIABILITY.md`](../docs/RELIABILITY.md) for the full architecture,
delivery guarantee, and configuration reference.

## What's not in this release

Framework-specific plugins and a real multi-event batch ingestion
endpoint (EP-16 currently accepts one event per request — see
`RELIABILITY.md`'s Batch Upload section) are staged for EP-18.4 — see
`../docs/ROADMAP.md`.

## Requirements

Node.js 18+ (for global `fetch`). Zero runtime dependencies.
