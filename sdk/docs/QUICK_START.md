# COSTORAH SDK Quick Start

Integrate COSTORAH in under two minutes.

## 1. Get an API key

Generate an Organization API Key from the COSTORAH dashboard (EP-14 — API
Keys page). It looks like `costorah_live_xxxxxxxxxxxxxxxxxxxx` and needs
the `usage:write` scope (the default scope for new keys).

## 2. Install

**Python**
```bash
pip install costorah
```

**JavaScript / TypeScript**
```bash
npm install @costorah/sdk
```

## 3. Track usage

**Python**
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

**JavaScript / TypeScript**
```ts
import { Costorah } from "@costorah/sdk";

const client = new Costorah({ apiKey: process.env.COSTORAH_API_KEY! });

await client.track({
  provider: "anthropic",
  model: "claude-sonnet-4",
  inputTokens: 200,
  outputTokens: 80,
  cost: 0.012,
  latencyMs: 410,
});
```

That's it — open the COSTORAH dashboard and the event is there.

## What happens under the hood

1. The SDK validates the payload locally (provider is in the supported
   catalog, tokens/cost are non-negative, etc.) — catching mistakes
   before a network call, and raising/rejecting immediately if invalid.
2. It's handed to the reliability layer (EP-18.3): `track()` itself
   returns immediately (<1ms) — it never blocks on the network.
3. In the background, it's authenticated with `Authorization: Bearer
   costorah_live_...` (EP-15) and POSTed to `{endpoint}/v1/ingest/usage`
   (EP-16), which stores the event and updates the dashboard's cost
   aggregates.
4. On a transient failure (network blip, 5xx, 429), it's retried with
   exponential backoff — indefinitely, never silently giving up — while
   your application keeps running. See `RELIABILITY.md` for the full
   pipeline (queueing, crash-durable persistence, circuit breaker,
   compression) and what this means for `track()`'s return value.

See `sdk/shared/API_CONTRACT.md` for the full wire contract, and each
language's own README (`sdk/python/README.md`, `sdk/javascript/README.md`)
for configuration, error handling, and what's not in this release yet.

## Next steps

- **Error handling** — catch `AuthenticationError`, `ValidationError`,
  `RateLimitError`, `ServerError`, `NetworkError` (see the language
  READMEs for exact import paths).
- **Configuration** — set a custom `endpoint`, `timeout`, or `max_retries`
  if you're testing against a non-default deployment.
- **Automatic instrumentation** — skip manual `track()` calls entirely
  for supported providers (OpenAI, Azure OpenAI, OpenRouter, Ollama,
  Grok, Anthropic, Mistral, Bedrock, Google Gemini, Cohere); see
  `AUTOMATIC_INSTRUMENTATION.md`.
- **Reliability** — queueing, crash-durable persistence, retry, circuit
  breaking, and compression are automatic and always on; see
  `RELIABILITY.md` for the architecture and `client.flush()`/
  `client.health()` if you need delivery confirmation.
- **What's next** — see `ROADMAP.md` for later EP-18 phases.
