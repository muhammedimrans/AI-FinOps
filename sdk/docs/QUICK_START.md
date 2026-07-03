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
   before a network call.
2. It authenticates with `Authorization: Bearer costorah_live_...`
   (EP-15).
3. It POSTs to `{endpoint}/v1/ingest/usage` (EP-16), which stores the
   event and updates the dashboard's cost aggregates immediately.
4. On a transient failure (network blip, 5xx, 429), it retries with
   exponential backoff (up to `maxRetries`, default 3) before surfacing
   an error to your code.

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
- **What's next** — see `ROADMAP.md` for background batching and other
  later EP-18 phases.
