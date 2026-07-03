# LangChain (JavaScript/TypeScript)

```ts
import { ChatOpenAI } from "@langchain/openai";
import { LangChainInstrumentor } from "@costorah/sdk";

await new LangChainInstrumentor().instrument();

const model = new ChatOpenAI({ model: "gpt-4o-mini" });
await model.invoke("Hello");   // usage, cost, latency, and trace context
                                 // are captured automatically
```

Requires `@langchain/core` as a peer dependency (optional — only needed if
you actually call `instrument()`).

## How it works

Hooks into `@langchain/core/context`'s `registerConfigureHook({ contextVar,
inheritable: true })` — the exact same `AsyncLocalStorage`-backed
extension point the Python `LangChainInstrumentor` uses (verified against
the real installed `@langchain/core` v0.3 source, not assumed from the
Python design). `CallbackManager._configureSync` reads whatever handler is
currently stored under `contextVar`, auto-injecting it into every run — no
`callbacks: [...]` argument needed at any call site.

## What gets captured

Same shape as the Python integration: `provider`, `model`, `input_tokens`,
`output_tokens`, `cost`, `finish_reason`, `trace_id`/`span_id`/
`parent_span_id`, and `chainName`/`toolName` enrichment read directly off
the parent run's own tracked entry.

## Two real bugs found during verification (not assumed)

**Callback handlers must extend the real `BaseCallbackHandler`.**
`CallbackManager`'s `isBaseCallbackHandler()` check duck-types on
`.copy`/`.awaitHandlers`, which only a true `BaseCallbackHandler` instance
carries — a plain object implementing only the handler *methods* is
silently never picked up.

**LangChain JS dispatches callbacks through a background queue by
default.** `awaitHandlers` (which controls whether `CallbackManager`
actually waits for a handler's returned promise before considering a run
complete) defaults to `false` unless `LANGCHAIN_CALLBACKS_BACKGROUND=false`
is set or the handler passes `_awaitHandler: true` to its constructor.
Without this, `handleLLMEnd`'s `await submit(...)` still ran — but only
*after* `model.invoke()` had already resolved, so a `client.flush()`
called right after `invoke()` would race the still-in-flight callback.

**Repeated `instrument()`/`uninstrument()` cycles are unsafe if
`setContextVariable` is called on every cycle.** `@langchain/core`'s own
`setContextVariable`/`getContextVariable` are themselves built on
`AsyncLocalStorage.enterWith`, which mutates whichever continuation
happens to resume at a given point rather than a call-stack-scoped value.
Three back-to-back instrument/uninstrument cycles (each separated by an
`await import(...)`) left an *earlier* cycle's handler permanently wired
into LangChain's dispatch, confirmed via a debug-tagged handler id.
`LangChainInstrumentor` now registers one persistent adapter exactly once
per process and flips a plain mutable delegate reference on every
subsequent `instrument()`/`uninstrument()` call, avoiding
`AsyncLocalStorage.enterWith` entirely after the first call.

All three were caught via this SDK's own test suite and a series of
increasingly targeted smoke scripts against the real `@langchain/openai`
package — not via code review alone.

## Provider resolution

Inferred primarily from the model name's prefix (`gpt-4o-mini` →
`openai`); falls back to LangChain JS's `lc_namespace` serialization path
(e.g. `["langchain", "chat_models", "openai", "ChatOpenAI"]` →
`langchain/chat_models/openai` → `openai`) — note this is LangChain's own
internal namespacing convention, *not* the npm package name
(`@langchain/openai` never appears in it). If neither resolves, no usage
event is submitted.

## Build note

`@langchain/core` is listed in `tsup.config.ts`'s `external` array — it
must never be bundled into `dist/`, or `LangChainInstrumentor` would load
a separate module instance than whatever a consumer's own
`@langchain/openai` resolves, breaking `registerConfigureHook`'s shared
singleton state (found empirically the same way as the bugs above).

## Verified against

Real `@langchain/openai` v0.3, with a `ChatOpenAI` instance whose
`configuration.fetch` is a fake `fetch` — the actual network boundary.
