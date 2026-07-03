# Vercel AI SDK (JavaScript/TypeScript)

```ts
import { openai } from "@ai-sdk/openai";
import { streamText } from "ai";
import { VercelAIInstrumentor } from "@costorah/sdk";

const instrumentor = new VercelAIInstrumentor();
instrumentor.instrument();

const model = instrumentor.wrapModel(openai("gpt-4o-mini"));
await streamText({ model, prompt: "Hello" });   // usage, cost, latency,
                                                  // and finish reason are
                                                  // captured automatically
```

Targets AI SDK v5's `LanguageModelV2` middleware architecture. Requires
`ai`/`@ai-sdk/*` as peer packages (only needed if you actually call
`wrapModel()`).

## Why every call site still needs `wrapModel()`, unlike the provider instrumentors

The provider instrumentors in this SDK (`OpenAIInstrumentor`,
`AnthropicInstrumentor`, ...) patch a shared class's prototype method
once, process-wide — every client instance and call site is covered after
a single `instrument()` call. The Vercel AI SDK has no equivalent global
interception point: `openai("gpt-4o-mini")` (and every other provider
package's model factory) returns a fresh, independent `LanguageModelV2`
plain object per call, and the `ai` package's own top-level functions
(`generateText`, `streamText`, ...) are plain ESM named exports, not
patchable from outside the module (verified by inspecting the installed
`ai` v5.0.210 and `@ai-sdk/openai` v2.0.110 packages' actual shape, not
assumed).

The AI SDK's own documented extension point for exactly this use case is
`wrapLanguageModel({ model, middleware })` — the same mechanism the SDK's
own built-in middleware uses. `wrapModel()` is a one-time setup step at
model-creation (analogous to `instrument()` itself), not a manual tracking
call at every request.

## What gets captured

`provider` (inferred from the model's own `provider` field, e.g.
`"openai.chat"` → `openai` — the part before the first `.`), `model`,
`input_tokens`/`output_tokens`/`total_tokens`, `reasoning_tokens`/
`cached_tokens` when reported, `cost`, `finish_reason`, `latency_ms`.
Covers both `generateText`/`generateObject` (non-streaming, via
`wrapGenerate`) and `streamText`/`streamObject` (via `wrapStream`, reading
usage off the stream's terminal `finish` part without buffering or
inspecting any text/tool-call content).

## Provider resolution

`model.provider` (e.g. `"openai.responses"`, `"anthropic.messages"`) is
split on `.`; the prefix is matched against known base providers. If it
doesn't resolve to a member of `SUPPORTED_PROVIDERS`, no usage event is
submitted.

## Never captured

Prompt content, response text/tool-call content are never read. The
stream-wrapping in `wrapStream` passes every chunk through unmodified —
only the terminal `finish` part's `usage`/`finishReason` fields are
inspected.

## Verified against

Real `@ai-sdk/openai` v2.0.110 + `ai` v5.0.210, using `createOpenAI({
fetch })` to intercept at the real network boundary and `generateText()`
end-to-end.
