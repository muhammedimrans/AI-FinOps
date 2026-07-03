# Automatic Instrumentation (EP-18.2)

Track AI usage without calling `track()` by hand. Instrument a provider
SDK once at startup, and every call through it is captured automatically —
comparable to OpenTelemetry Auto Instrumentation, Sentry, Datadog APM, or
LangSmith Tracing.

```python
from openai import OpenAI
from costorah.instrumentation import OpenAIInstrumentor

OpenAIInstrumentor().instrument()

client = OpenAI()
client.chat.completions.create(model="gpt-4o", messages=[...])  # tracked automatically
```

```typescript
import OpenAI from "openai";
import { OpenAIInstrumentor } from "@costorah/sdk";

new OpenAIInstrumentor().instrument();

const client = new OpenAI();
await client.chat.completions.create({ model: "gpt-4o", messages: [] }); // tracked automatically
```

## How it works

Each provider has an `Instrumentor` class implementing a common interface:
`instrument()`, `uninstrument()`, `isInstrumented()`, `extractUsage()`,
`normalize()`. `instrument()` safely monkey-patches the provider SDK's
official public method(s) — never internal/private APIs — so every call
made through that SDK is intercepted, timed, and (on completion) submitted
as a COSTORAH usage event via the EP-18.1 SDK core's `track()`. No prompt
or response content is ever read or stored — only usage metadata (see
[Privacy](#privacy)).

`uninstrument()` restores the exact original method, so instrumented code
behaves identically to unpatched code once removed.

## Supported providers

| Provider | Python | JavaScript |
|---|---|---|
| OpenAI | `OpenAIInstrumentor` | `OpenAIInstrumentor` |
| Azure OpenAI | `AzureOpenAIInstrumentor` | `AzureOpenAIInstrumentor` |
| OpenRouter | `OpenRouterInstrumentor` | `OpenRouterInstrumentor` |
| Ollama | `OllamaInstrumentor` | `OllamaInstrumentor` |
| Grok (xAI) | `GrokInstrumentor` | `GrokInstrumentor` |
| Anthropic | `AnthropicInstrumentor` | `AnthropicInstrumentor` |
| Mistral | `MistralInstrumentor` | `MistralInstrumentor` |
| Amazon Bedrock (Converse API) | `BedrockInstrumentor` | `BedrockInstrumentor` |
| Google Gemini | `GeminiInstrumentor` | `GeminiInstrumentor` (`instrument(client)`) |
| Cohere | `CohereInstrumentor` | `CohereInstrumentor` (`instrument(client)`) |

OpenAI, Azure OpenAI, OpenRouter, Ollama, and Grok are all accessed
through the official `openai` package (OpenRouter/Ollama/Grok publish
OpenAI-compatible endpoints) and share one physical patch under the hood
— instrumenting `OpenAIInstrumentor` alone does **not** capture traffic
through an `AzureOpenAI` client; each provider's own instrumentor must be
instrumented for its traffic to be captured. Provider identity for each
call is resolved from the client's `base_url`/`baseURL` (or class name
for Azure), so multiple family members can be instrumented at once safely
— uninstrumenting one never breaks another still-active sibling.

### Google Gemini and Cohere: `instrument(client)`

Every other provider's SDK exposes its request method on a shared
prototype/class, so a single zero-argument `instrument()` patches it for
every client instance process-wide. `@google/genai`'s
`generateContent`/`generateContentStream` and `cohere-ai`'s
`chat`/`chatStream` are declared as **instance-level** functions instead
(confirmed via each package's own type declarations and property
descriptors) — there is no shared prototype to patch once. These two
instrumentors therefore take the specific client instance to wrap:

```python
from google import genai
from costorah.instrumentation import GeminiInstrumentor

client = genai.Client()
GeminiInstrumentor().instrument(client)  # note: takes the client, not zero-arg
client.models.generate_content(model="gemini-1.5-pro", contents="Hello")
```

```typescript
import { GoogleGenAI } from "@google/genai";
import { GeminiInstrumentor } from "@costorah/sdk";

const client = new GoogleGenAI({ apiKey: "..." });
new GeminiInstrumentor().instrument(client);
await client.models.generateContent({ model: "gemini-1.5-pro", contents: "Hello" });
```

Calling `instrument()` with no client on these two raises
`InstrumentationError` with an explanation, rather than silently doing
nothing.

## Streaming support

Streamed responses are supported for every provider that streams. Chunks
are yielded to your code immediately and untouched — nothing is buffered
beyond what's needed to read the final usage totals once the stream
completes. Telemetry is submitted exactly once, after the stream finishes
(success or error), using the final token counts and total latency —
never mid-stream.

## Async support

Python: both sync and async client methods are instrumented (`.create()`
and `.acreate()`-style equivalents, or the SDK's async client classes).
JavaScript: every provider SDK here is Promise/async-native, so
instrumentation wraps the async methods directly — `await` works exactly
as it does uninstrumented.

## Error handling

Success, timeouts, cancellations, rate limits, and provider/network
errors are all captured with `status` set accordingly and zeroed token
counts (a failed call has no real usage to report). The original error is
always re-thrown/re-raised to your code unchanged — instrumentation never
swallows or alters a provider SDK's own error behavior. Telemetry
submission itself is always best-effort: if COSTORAH is unreachable or
misconfigured, the failure is logged and swallowed, never raised into
your AI request.

## Cost calculation

If a provider's response doesn't include cost, instrumentation computes
it from a small table of well-known providers/models (reusing the
per-token pricing convention documented in `sdk/shared/API_CONTRACT.md`
and mirrored between `costorah/instrumentation/pricing.py` and
`src/instrumentation/pricing.ts`). For a model not in that table, cost is
reported as `0` with `metadata.cost_estimated` (Python) /
`metadata.costEstimated` (JavaScript) set to `false` — instrumentation
never guesses a cost figure for an unrecognized model.

## Privacy

Instrumentation **never** captures prompt text, completion text, images,
files, audio, or embeddings — only usage metadata: provider, model,
token counts, latency, status, request ID, and timestamp. This is
enforced by design: every `extractUsage()` implementation reads only a
response's `usage`/token-count fields, never its content fields, and this
is covered by dedicated tests per provider (asserting captured payloads
never contain the literal prompt/completion text used in the test).
Structured logging follows the same rule and additionally never logs API
keys or other secrets (see EP-18.1's logging redaction, reused as-is
here).

## Configuration

```python
OpenAIInstrumentor(
    enabled=True,          # set False to disable globally without removing the call
    capture_metadata=True, # include cost_estimated (and similar) in metadata
    calculate_cost=True,   # compute cost when the provider response doesn't include one
    client=my_client,      # explicit Costorah client; defaults to one built from
                            # COSTORAH_API_KEY / COSTORAH_ENDPOINT env vars
)
```

```typescript
new OpenAIInstrumentor({
  enabled: true,
  captureMetadata: true,
  calculateCost: true,
  client: myClient,
});
```

## Framework compatibility

Instrumentation patches the provider SDK itself, not any web framework —
it works identically under FastAPI, Flask, Django, Express, Next.js, or a
bare Node.js/Python script. Call `instrument()` once at process startup
(e.g. before your framework starts serving requests); there is no
framework-specific integration code.

## Troubleshooting

- **`InstrumentationError: The '<package>' package is not installed`** —
  install the provider SDK package the instrumentor targets (e.g.
  `pip install openai` / `npm install openai`). Instrumentors detect the
  installed package at `instrument()` time and fail with this message
  rather than silently doing nothing.
- **No events showing up** — confirm `COSTORAH_API_KEY` is set (or an
  explicit `client`/`Costorah` instance was passed), and that the client
  you're calling was constructed the same way the instrumented family
  member expects (e.g. an `AzureOpenAI` client needs
  `AzureOpenAIInstrumentor`, not just `OpenAIInstrumentor`).
- **Google Gemini / Cohere calls not tracked** — these two require
  `instrument(client)` with the specific client instance; a bare
  `instrument()` raises `InstrumentationError` rather than silently
  no-op'ing.
- **Cost always `0`** — the model isn't in the built-in pricing table;
  this is intentional (see [Cost calculation](#cost-calculation)) rather
  than a bug. Check `metadata.cost_estimated`/`costEstimated`.

## Migration from manual `track()`

No migration is required — automatic instrumentation and manual `track()`
calls compose freely; use `Costorah.track()` directly for anything an
instrumentor doesn't cover, and instrumentation for the providers it
does. To move a manual integration to automatic instrumentation, remove
the manual `track()` calls surrounding your provider SDK calls and add
the matching `instrument()` call once at startup — the two are not meant
to be used together for the same call (that would double-submit usage
for it).

## What's out of scope here

Batch upload, an offline/retry queue, network-request compression,
framework-specific plugins, and CI/CD publishing are EP-18.3/EP-18.4
concerns — see `sdk/docs/ROADMAP.md`.
