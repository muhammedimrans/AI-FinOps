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

That's it — the event is authenticated (EP-15), validated, and pushed to
COSTORAH's Usage Ingestion API (EP-16), rejecting with a `Costorah*Error`
if anything goes wrong instead of failing silently.

Ships as both ESM and CommonJS with bundled `.d.ts` types — works from
`import` or `require()`, Node 18+.

## Configuration

```ts
const client = new Costorah({
  apiKey: "costorah_live_xxxxxxxxx",
  endpoint: "https://api.costorah.com", // default
  timeout: 30, // seconds, per HTTP request
  maxRetries: 3, // bounded retry for track() — see "Retry behavior" below
  verifyTls: true,
});
```

`batchSize` and `flushInterval` are accepted for forward compatibility
with EP-18.3 (background batching) but have no effect yet — every
`track()` call in this release makes its own HTTP request immediately.

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

console.log(result.usageId, result.duplicate);
```

Supported `provider` values: `openai`, `anthropic`, `grok`, `google`,
`azure_openai`, `openrouter`, `ollama`, `cohere`, `bedrock`, `mistral`.

Reusing the same `requestId` across calls is safe — COSTORAH treats it as
an idempotency key and returns the original record with `duplicate: true`
instead of double-counting. If you don't supply one, the SDK generates a
random one per call.

## Error handling

```ts
import {
  AuthenticationError,
  ValidationError,
  RateLimitError,
  ServerError,
  NetworkError,
} from "@costorah/sdk";

try {
  await client.track({ provider: "openai", model: "gpt-4.1", cost: 0.01 });
} catch (err) {
  if (err instanceof AuthenticationError) {
    // invalid/expired API key, or the key lacks usage:write — not retried
  } else if (err instanceof ValidationError) {
    // the payload itself was rejected — not retried
  } else if (
    err instanceof RateLimitError ||
    err instanceof ServerError ||
    err instanceof NetworkError
  ) {
    // already retried internally up to maxRetries; still failed
  }
}
```

Client-side validation (unsupported provider, negative tokens, etc.) also
throws `ValidationError`, saving a round trip for errors the SDK can catch
locally.

## Retry behavior

Transient failures (`RateLimitError`, `ServerError`, `NetworkError`) are
retried automatically with exponential backoff — `1, 2, 4, 8, 16, 30, 60`
seconds, honoring a `Retry-After` header when the server sends one — up to
`maxRetries` (default 3) before the error is thrown to your code.
`AuthenticationError` and `ValidationError` are never retried, since
resending an unchanged bad request or an invalid key can't succeed.

This is a bounded retry appropriate for an awaited call in your request
path. A non-blocking background queue with unlimited retry and offline
persistence — conceptually similar to the
[Monitoring Agent](../../monitoring-agent)'s design — is planned for
EP-18.3.

## Concurrency

Safe for concurrent async operations: a single `Costorah` instance can be
`await`ed from many places at once (e.g. many in-flight request handlers
in the same Node process). Each `track()` call is independent and holds
no shared mutable state.

## Logging

The SDK logs retry attempts through a small built-in console logger with
redaction baked in (API keys and other sensitive values are stripped from
every log line, even accidentally). Supply your own logger — e.g. to
route into pino or winston — via the SDK's internal logger hook if you
need structured log aggregation; see `src/logging.ts`'s `Logger`
interface.

## What's not in this release

Automatic provider-response detection (`client.trackOpenAI(response)`),
auto-instrumentation, background batching/queueing, and framework
integrations are staged for later phases (EP-18.2–EP-18.4) — see
`../docs/ROADMAP.md`. This release covers manual `track()`, which is fully
production-ready on its own.

## Requirements

Node.js 18+ (for global `fetch`). Zero runtime dependencies.
