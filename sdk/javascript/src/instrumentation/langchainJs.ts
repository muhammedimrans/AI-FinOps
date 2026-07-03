/**
 * LangChainInstrumentor — automatic usage capture for `@langchain/core`
 * (JS/TS LangChain), mirroring the Python SDK's
 * `costorah.instrumentation.langchain` design exactly — see that
 * module's docstring for the full architectural rationale, which applies
 * here unchanged.
 *
 *     import { ChatOpenAI } from "@langchain/openai";
 *     import { LangChainInstrumentor } from "@costorah/sdk";
 *
 *     await new LangChainInstrumentor().instrument();
 *
 *     const chain = prompt.pipe(new ChatOpenAI({ model: "gpt-4o-mini" }));
 *     await chain.invoke({ topic: "otters" });   // usage, cost, latency,
 *                                                  // and trace context
 *                                                  // are captured
 *                                                  // automatically —
 *                                                  // zero manual
 *                                                  // tracking calls
 *
 * ## The extension point
 *
 * `@langchain/core/context`'s `registerConfigureHook({ contextVar,
 * inheritable: true })` is LangChain JS's own, official mechanism for
 * auto-injecting a callback handler into every run's callback manager
 * without any `callbacks: [...]` argument at any call site —
 * `CallbackManager._configureSync` (the same static method every
 * `invoke()`/`stream()` call goes through) iterates the registered hooks
 * and reads whatever handler is currently stored under `contextVar` via
 * `getContextVariable()`/`setContextVariable()` (an `AsyncLocalStorage`-
 * backed context variable — the JS equivalent of Python's
 * `contextvars.ContextVar`, and the exact same mechanism LangSmith's own
 * `LANGCHAIN_TRACING_V2` auto-tracer uses internally). Verified by
 * reading the actual installed `@langchain/core` (v0.3.x) package's
 * source, not assumed from the Python SDK's design.
 *
 * ## What gets submitted as real usage telemetry, and what doesn't
 *
 * Every `handleLLMEnd`/`handleChatModelStart` pair for a real, completed
 * LLM call submits a usage event through the existing
 * `costorah.instrumentation.submission`/reliability pipeline, using
 * LangChain's own standardized `AIMessage.usage_metadata` shape
 * (`input_tokens`/`output_tokens`/`total_tokens`, with
 * `output_token_details.reasoning`/`input_token_details.cache_read` when
 * present) when available, falling back to `llmOutput.tokenUsage` for
 * non-chat LLMs. If the provider can't be resolved to a member of
 * `SUPPORTED_PROVIDERS` (inferred from the LangChain integration
 * package's module path, e.g. `@langchain/openai` -> `openai`, falling
 * back to the model name's prefix), **no usage event is submitted**.
 *
 * Chain/tool lifecycle events (`handleChainStart`/`handleToolStart` and
 * their `*End`/`*Error` counterparts) don't independently submit usage —
 * they enrich a nested LLM call's metadata by name/kind, read directly
 * off the parent run's own tracked entry (looked up by `parentRunId`)
 * when `handleLLMEnd` fires. An earlier version of this instrumentor
 * used ambient `AsyncLocalStorage` context (`enterWith`/manual restore,
 * mirroring the Python LangChainInstrumentor's `request_context(...)`
 * push/pop) instead — found empirically, via this SDK's own test suite,
 * to race with the reliability layer's background worker: `enterWith`
 * mutates whichever continuation happens to resume at that point, not a
 * call-stack-scoped value, so a still-in-flight background task from an
 * earlier span could silently reinstate stale context after a later
 * span's restore already ran. Reading parent/child relationships
 * directly off `runId`/`parentRunId` (already used for `traceId`/
 * `spanId`/`parentSpanId`) sidesteps the whole class of bug — the same
 * "read structured data directly, don't track ambient state across
 * separate callback invocations" fix `costorah.instrumentation.crewai`
 * applied for an unrelated but analogous reason (its event bus's
 * thread-pool dispatch).
 *
 * ## Never captured
 *
 * Prompt/message content, response content, and tool
 * input/output are never read by this instrumentor — only
 * name/ID/token-count/timing/finish-reason fields are.
 */

import { InstrumentationError } from "./base.js";
import { calculateCost } from "./pricing.js";
import { submit } from "./submission.js";
import type { ExtractedUsage } from "./base.js";
import type { Costorah } from "../client.js";
import type { UsageStatus } from "../types.js";

/** This module has no static/top-level import of `@langchain/core` —
 * unlike the provider instrumentors' patched SDKs, LangChain isn't
 * needed just to *load* `@costorah/sdk`; only `instrument()` needs it
 * present. `@langchain/core`'s real `BaseCallbackHandler` is resolved
 * lazily, inside `instrument()`, via a dynamic `import()` — deliberately
 * *not* `createRequire` (the mechanism `_dualPackage.ts` uses for
 * prototype patching): `registerConfigureHook`'s hook list and
 * `setContextVariable`'s backing store are module-level singletons
 * inside `@langchain/core/context`, and `require()`-ing the package's
 * CJS build while `@langchain/openai` (an ESM package) resolves the
 * *ESM* build internally loads two independent module instances with
 * two independent singletons — `setContextVariable` would write to one
 * copy's store while `CallbackManager._configureSync` reads from the
 * other, silently never firing. Found empirically: an earlier version
 * of this instrumentor used `createRequire` here and every
 * `handleLLMEnd` callback simply never fired, exactly as when the
 * adapter class didn't extend `BaseCallbackHandler` at all (a second,
 * unrelated bug hit and fixed in the same debugging pass — see the
 * adapter class below). Dynamic `import()` resolves through the same
 * ESM condition every ESM consumer (like `@langchain/openai`) uses,
 * guaranteeing the same module instance. */
interface BaseCallbackHandlerCtor {
  new (input?: unknown): Record<string, unknown>;
}

interface LangChainCore {
  BaseCallbackHandler: BaseCallbackHandlerCtor;
  registerConfigureHook: (config: { contextVar?: string; inheritable?: boolean }) => void;
  setContextVariable: (name: PropertyKey, value: unknown) => void;
}

// Memoized after the first successful load. Not just an optimization:
// `@langchain/core`'s own `setContextVariable`/`getContextVariable` are
// themselves built on `AsyncLocalStorage.enterWith`, which — as this
// module's own chain/tool tracking discovered the hard way (see the
// module docstring) — is unsafe across overlapping/interleaved async
// operations within the same top-level continuation. Every extra
// `await import(...)` in `instrument()`/`uninstrument()` is one more
// microtask boundary where a *different*, still-in-flight
// instrument()/uninstrument() cycle's continuation could resume and
// clobber the context variable via its own `enterWith` call. Found
// empirically: three back-to-back `instrument()`/`uninstrument()`
// cycles (each awaiting a fresh `import()`) on three separate
// `LangChainInstrumentor` instances left the *first* cycle's handler
// permanently wired into LangChain's callback dispatch — confirmed via
// a unique debug id tagged on each handler instance — even though the
// third cycle's `getContextVariable()` read-back immediately after its
// own `instrument()` call correctly showed its own handler. Memoizing
// this load means only the *first-ever* `instrument()` call in a
// process awaits an `import()` at all; every subsequent call resolves
// synchronously-ish off the cached promise, eliminating most of the
// extra interleaving windows this bug depends on.
let cachedCore: Promise<LangChainCore> | undefined;

function loadLangChainCore(): Promise<LangChainCore> {
  if (!cachedCore) {
    cachedCore = (async () => {
      try {
        const [baseMod, contextMod] = await Promise.all([
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          import("@langchain/core/callbacks/base") as Promise<any>,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          import("@langchain/core/context") as Promise<any>,
        ]);
        return {
          BaseCallbackHandler: baseMod.BaseCallbackHandler,
          registerConfigureHook: contextMod.registerConfigureHook,
          setContextVariable: contextMod.setContextVariable,
        };
      } catch {
        cachedCore = undefined;
        throw new InstrumentationError(
          "The '@langchain/core' package is not installed. Install it with " +
            "`npm install @langchain/core` to use LangChainInstrumentor.",
        );
      }
    })();
  }
  return cachedCore;
}

const _MODEL_PREFIX_TO_PROVIDER: [string, string][] = [
  ["gpt-", "openai"],
  ["o1-", "openai"],
  ["o3-", "openai"],
  ["chatgpt-", "openai"],
  ["text-embedding-", "openai"],
  ["claude-", "anthropic"],
  ["gemini-", "google"],
  ["command-", "cohere"],
  ["mistral-", "mistral"],
  ["mixtral-", "mistral"],
  ["grok-", "grok"],
];

/** Prefixes match the `lc_namespace` path LangChain JS embeds in every
 * serialized class (`model.toJSON().id`, and the `id` field
 * `handleChatModelStart`/`handleLLMStart` receive) — verified against
 * the real installed `@langchain/openai` package, whose `ChatOpenAI`
 * serializes as `["langchain", "chat_models", "openai", "ChatOpenAI"]`.
 * This is LangChain's own internal namespacing convention, *not* the
 * npm package name (`@langchain/openai` never appears in it) — a
 * mismatch from what the Python SDK's equivalent module-path list uses,
 * since `langchain_openai`'s Python import path and its JS npm package
 * name happen to coincide but the JS *serialization* id does not. Model-
 * name-based inference (`inferProviderFromModel`) is more reliable
 * across the board and is tried first (see `startLlmSpan`'s
 * `providerHint` usage) — module-path inference is a fallback for
 * models whose name alone doesn't reveal the provider. */
const _MODULE_PREFIX_TO_PROVIDER: [string, string][] = [
  ["langchain/chat_models/openai", "openai"],
  ["langchain/chat_models/anthropic", "anthropic"],
  ["langchain/chat_models/google", "google"],
  ["langchain/chat_models/mistralai", "mistral"],
  ["langchain/chat_models/cohere", "cohere"],
  ["langchain/chat_models/bedrock", "bedrock"],
  ["langchain/chat_models/ollama", "ollama"],
];

export function inferProviderFromModel(model: string | undefined): string | undefined {
  if (!model) return undefined;
  const lowered = model.toLowerCase();
  for (const [prefix, provider] of _MODEL_PREFIX_TO_PROVIDER) {
    if (lowered.startsWith(prefix)) return provider;
  }
  return undefined;
}

export function inferProviderFromModulePath(modulePath: string | undefined): string | undefined {
  if (!modulePath) return undefined;
  for (const [prefix, provider] of _MODULE_PREFIX_TO_PROVIDER) {
    if (modulePath.startsWith(prefix)) return provider;
  }
  return undefined;
}

interface UsageMetadataLike {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_token_details?: { cache_read?: number };
  output_token_details?: { reasoning?: number };
}

interface GenerationLike {
  generationInfo?: Record<string, unknown>;
  message?: {
    usage_metadata?: UsageMetadataLike;
    response_metadata?: { model_name?: string; model?: string };
  };
}

interface LLMResultLike {
  generations: GenerationLike[][];
  llmOutput?: {
    model_name?: string;
    model?: string;
    tokenUsage?: { promptTokens?: number; completionTokens?: number; totalTokens?: number };
  };
}

export interface ExtractedLangChainUsage {
  model: string | undefined;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number | undefined;
  cachedTokens: number | undefined;
  reasoningTokens: number | undefined;
}

export function extractUsageMetadata(result: LLMResultLike): ExtractedLangChainUsage | undefined {
  const topLevelModel = result.llmOutput?.model_name ?? result.llmOutput?.model;
  for (const generationList of result.generations) {
    for (const generation of generationList) {
      const usage = generation.message?.usage_metadata;
      if (usage) {
        // ChatOpenAI (and, per the same LangChain JS convention, every
        // other @langchain/* chat model) puts the model name on the
        // message's own response_metadata, not llmOutput — found
        // empirically: llmOutput only carried a duplicate tokenUsage
        // for ChatOpenAI, never model_name/model, so relying solely on
        // llmOutput silently produced `model: undefined` for every real
        // call.
        const model =
          generation.message?.response_metadata?.model_name ??
          generation.message?.response_metadata?.model ??
          topLevelModel;
        return {
          model,
          inputTokens: usage.input_tokens,
          outputTokens: usage.output_tokens,
          totalTokens: usage.total_tokens,
          cachedTokens: usage.input_token_details?.cache_read,
          reasoningTokens: usage.output_token_details?.reasoning,
        };
      }
    }
  }
  const tokenUsage = result.llmOutput?.tokenUsage;
  if (tokenUsage) {
    return {
      model: topLevelModel,
      inputTokens: tokenUsage.promptTokens ?? 0,
      outputTokens: tokenUsage.completionTokens ?? 0,
      totalTokens: tokenUsage.totalTokens,
      cachedTokens: undefined,
      reasoningTokens: undefined,
    };
  }
  return undefined;
}

export function extractFinishReason(result: LLMResultLike): string | undefined {
  for (const generationList of result.generations) {
    for (const generation of generationList) {
      const reason = generation.generationInfo?.finish_reason;
      if (typeof reason === "string") return reason;
    }
  }
  return undefined;
}

interface RunInfo {
  kind: "chain" | "tool" | "llm";
  name: string | undefined;
  traceId: string;
  spanId: string;
  start: number;
  providerHint: string | undefined;
}

function newId(prefix: string): string {
  return `${prefix}_${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`;
}

function serializedModulePath(serialized: { id?: string[] }): string | undefined {
  const id = serialized.id;
  if (!id || id.length < 2) return undefined;
  return id.slice(0, -1).join("/");
}

/** Holds all of LangChain callback-event capture logic. Directly
 * instantiable and testable without `@langchain/core` installed — see
 * this module's top-of-file note for why `instrument()` wraps an
 * instance of this class in a small adapter that extends the real
 * `BaseCallbackHandler` rather than this class extending it directly. */
export class CostorahLangChainHandler {
  name = "costorah_langchain_handler";
  private readonly runs = new Map<string, RunInfo>();
  private eventsCapturedTotal = 0;
  private readonly client: Costorah | undefined;
  private readonly calculateCostEnabled: boolean;

  constructor(
    options: { client?: Costorah | undefined; calculateCost?: boolean | undefined } = {},
  ) {
    this.client = options.client;
    this.calculateCostEnabled = options.calculateCost ?? true;
  }

  get eventsCaptured(): number {
    return this.eventsCapturedTotal;
  }

  handleLLMStart = (
    llm: { id?: string[] },
    _prompts: string[],
    runId: string,
    parentRunId?: string,
  ): void => {
    this.startLlmSpan(llm, runId, parentRunId);
  };

  handleChatModelStart = (
    llm: { id?: string[] },
    _messages: unknown[],
    runId: string,
    parentRunId?: string,
  ): void => {
    this.startLlmSpan(llm, runId, parentRunId);
  };

  private startLlmSpan(llm: { id?: string[] }, runId: string, parentRunId?: string): void {
    this.eventsCapturedTotal += 1;
    const parent = parentRunId ? this.runs.get(parentRunId) : undefined;
    this.runs.set(runId, {
      kind: "llm",
      name: undefined,
      traceId: parent?.traceId ?? newId("trace"),
      spanId: runId,
      start: Date.now(),
      providerHint: inferProviderFromModulePath(serializedModulePath(llm)),
    });
  }

  // Async and awaited by the callback manager (BaseCallbackHandler's
  // handle* methods may return Promise<any>, which LangChain awaits
  // before considering the run complete) — matches the existing
  // provider instrumentors' `await submit(...)` pattern
  // (openaiCompatible.ts) rather than a fire-and-forget `void submit`,
  // so a `client.flush()` called right after `invoke()` resolves
  // reliably has the event already enqueued.
  handleLLMEnd = async (
    output: LLMResultLike,
    runId: string,
    parentRunId?: string,
  ): Promise<void> => {
    this.eventsCapturedTotal += 1;
    const info = this.runs.get(runId);
    this.runs.delete(runId);
    if (!info) return;

    const usage = extractUsageMetadata(output);
    if (!usage) return;
    const provider = inferProviderFromModel(usage.model) ?? info.providerHint;
    if (!provider) return;

    const latencyMs = Date.now() - info.start;
    const { cost, estimated } = this.calculateCostEnabled
      ? calculateCost(provider, usage.model ?? "unknown", usage.inputTokens, usage.outputTokens)
      : { cost: 0, estimated: false };

    const metadata: Record<string, unknown> = {
      traceId: info.traceId,
      spanId: info.spanId,
      parentSpanId: parentRunId ?? null,
      framework: "langchain",
      costEstimated: estimated,
    };
    const finishReason = extractFinishReason(output);
    if (finishReason) metadata.finishReason = finishReason;
    if (usage.reasoningTokens !== undefined) metadata.reasoningTokens = usage.reasoningTokens;
    if (usage.cachedTokens !== undefined) metadata.cachedTokens = usage.cachedTokens;

    // Chain/tool name enrichment is read directly from the parent run's
    // own tracked RunInfo (looked up by parentRunId), not via ambient
    // AsyncLocalStorage context — see this module's top-of-file note on
    // why the ambient-context approach (mirroring the Python
    // LangChainInstrumentor's request_context() enrichment) was
    // abandoned here.
    const parentInfo = parentRunId ? this.runs.get(parentRunId) : undefined;
    if (parentInfo?.kind === "chain" && parentInfo.name) metadata.chainName = parentInfo.name;
    if (parentInfo?.kind === "tool" && parentInfo.name) metadata.toolName = parentInfo.name;

    const status: UsageStatus = "success";
    const extracted: ExtractedUsage = {
      provider,
      model: usage.model ?? "unknown",
      inputTokens: usage.inputTokens,
      outputTokens: usage.outputTokens,
      cachedTokens: usage.cachedTokens,
      totalTokens: usage.totalTokens,
      cost,
      currency: "USD",
      latencyMs,
      status,
      requestId: newId("sdk_js_langchain"),
      timestamp: new Date(),
      metadata,
    };
    await submit(extracted, this.client);
  };

  handleLLMError = (_err: unknown, runId: string): void => {
    this.eventsCapturedTotal += 1;
    this.runs.delete(runId);
  };

  handleChainStart = (
    chain: { id?: string[] },
    _inputs: unknown,
    runId: string,
    parentRunId?: string,
  ): void => {
    this.startSpan("chain", chain, runId, parentRunId);
  };

  handleChainEnd = (_outputs: unknown, runId: string): void => {
    this.endSpan(runId);
  };

  handleChainError = (_err: unknown, runId: string): void => {
    this.endSpan(runId);
  };

  handleToolStart = (
    tool: { id?: string[]; name?: string },
    _input: string,
    runId: string,
    parentRunId?: string,
  ): void => {
    this.startSpan("tool", tool, runId, parentRunId);
  };

  handleToolEnd = (_output: unknown, runId: string): void => {
    this.endSpan(runId);
  };

  handleToolError = (_err: unknown, runId: string): void => {
    this.endSpan(runId);
  };

  private startSpan(
    kind: "chain" | "tool",
    serialized: { id?: string[]; name?: string },
    runId: string,
    parentRunId: string | undefined,
  ): void {
    this.eventsCapturedTotal += 1;
    const parent = parentRunId ? this.runs.get(parentRunId) : undefined;
    const name = serialized.name ?? serialized.id?.[serialized.id.length - 1] ?? kind;
    this.runs.set(runId, {
      kind,
      name,
      traceId: parent?.traceId ?? newId("trace"),
      spanId: runId,
      start: Date.now(),
      providerHint: undefined,
    });
  }

  private endSpan(runId: string): void {
    this.eventsCapturedTotal += 1;
    this.runs.delete(runId);
  }
}

export interface LangChainInstrumentorOptions {
  client?: Costorah;
  calculateCost?: boolean;
}

const CONTEXT_VAR_NAME = "__costorah_langchain_handler__";

/** Holds whichever `CostorahLangChainHandler` is currently "active" —
 * i.e. whichever `LangChainInstrumentor` most recently called
 * `instrument()` without a matching `uninstrument()` yet. A plain JS
 * closure variable, not `AsyncLocalStorage`-backed, deliberately: see
 * `sharedAdapter()`'s docstring for why. */
interface SharedAdapterState {
  active: CostorahLangChainHandler | undefined;
}

let sharedAdapterPromise: Promise<SharedAdapterState> | undefined;

/** Builds (once, ever, per process) a single long-lived adapter instance
 * registered with `@langchain/core` via `registerConfigureHook`/
 * `setContextVariable`, and returns a mutable `{ active }` box that
 * every `instrument()`/`uninstrument()` call after the first one simply
 * flips — `setContextVariable` (and therefore `AsyncLocalStorage.
 * enterWith`, on which it's built) is called **exactly once** for the
 * lifetime of the process.
 *
 * This matters for correctness, not just efficiency: an earlier version
 * called `setContextVariable` on every `instrument()`/`uninstrument()`
 * call. Found empirically (via this SDK's own test suite failing in a
 * way that only reproduced across multiple sequential
 * instrument()/uninstrument() cycles, each separated by an `await`):
 * `@langchain/core`'s `setContextVariable`/`getContextVariable` are
 * themselves built on `AsyncLocalStorage.enterWith`, which mutates
 * whichever continuation happens to resume at that point rather than a
 * call-stack-scoped value — the exact same class of bug this module's
 * own (now-removed) ambient chain/tool context tracking hit. Three
 * back-to-back instrument()/uninstrument() cycles on three separate
 * `LangChainInstrumentor` instances left the *first* cycle's handler
 * permanently wired into LangChain's dispatch, even though each later
 * cycle's own `getContextVariable()` read-back immediately after its
 * `instrument()` call correctly showed its own handler — a subsequent,
 * still-in-flight `enterWith` from an earlier cycle silently overwrote
 * it. Delegating through one persistent adapter and a plain mutable
 * `active` reference — read at call time, not captured once at
 * registration time — sidesteps `enterWith`'s instability entirely for
 * every call after the first. */
function sharedAdapter(): Promise<SharedAdapterState> {
  if (!sharedAdapterPromise) {
    sharedAdapterPromise = (async () => {
      const { BaseCallbackHandler, registerConfigureHook, setContextVariable } =
        await loadLangChainCore();
      const state: SharedAdapterState = { active: undefined };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      type AnyArgs = any[];

      class CostorahCallbackAdapter extends BaseCallbackHandler {
        name = "costorah_langchain_handler";

        constructor(input?: unknown) {
          super(input);
          // `_awaitHandler: true` (passed below) sets `awaitHandlers`
          // via the base constructor, but `copy()` — which
          // `CallbackManager` calls when building a run-specific
          // manager — does `new this.constructor(this)`, passing the
          // *instance* (whose own key is `awaitHandlers`, not
          // `_awaitHandler`) as input, silently dropping the flag on
          // every copy. Forcing it again here, after `super()`,
          // survives `copy()` because `copy()` invokes this exact
          // constructor again. Required because LangChain JS dispatches
          // callback handlers through a background `p-queue` by
          // *default* (`awaitHandlers` defaults to the
          // `LANGCHAIN_CALLBACKS_BACKGROUND` env var, unset by
          // default) — without this, `handleLLMEnd`'s `await
          // submit(...)` still ran, but only after `model.invoke()`
          // had already resolved, racing a `client.flush()` called
          // right after.
          this.awaitHandlers = true;
        }

        handleLLMStart = (...args: AnyArgs): unknown =>
          (state.active?.handleLLMStart as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
        handleChatModelStart = (...args: AnyArgs): unknown =>
          (
            state.active?.handleChatModelStart as ((...a: AnyArgs) => unknown) | undefined
          )?.(...args);
        handleLLMEnd = (...args: AnyArgs): unknown =>
          (state.active?.handleLLMEnd as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
        handleLLMError = (...args: AnyArgs): unknown =>
          (state.active?.handleLLMError as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
        handleChainStart = (...args: AnyArgs): unknown =>
          (state.active?.handleChainStart as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
        handleChainEnd = (...args: AnyArgs): unknown =>
          (state.active?.handleChainEnd as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
        handleChainError = (...args: AnyArgs): unknown =>
          (state.active?.handleChainError as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
        handleToolStart = (...args: AnyArgs): unknown =>
          (state.active?.handleToolStart as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
        handleToolEnd = (...args: AnyArgs): unknown =>
          (state.active?.handleToolEnd as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
        handleToolError = (...args: AnyArgs): unknown =>
          (state.active?.handleToolError as ((...a: AnyArgs) => unknown) | undefined)?.(...args);
      }

      registerConfigureHook({ contextVar: CONTEXT_VAR_NAME, inheritable: true });
      setContextVariable(CONTEXT_VAR_NAME, new CostorahCallbackAdapter({ _awaitHandler: true }));
      return state;
    })();
  }
  return sharedAdapterPromise;
}

export class LangChainInstrumentor {
  private handler: CostorahLangChainHandler | undefined;
  private readonly client: Costorah | undefined;
  private readonly calculateCostEnabled: boolean;

  constructor(options: LangChainInstrumentorOptions = {}) {
    this.client = options.client;
    this.calculateCostEnabled = options.calculateCost ?? true;
  }

  /** Async — unlike the Python SDK's synchronous `instrument()`,
   * because loading `@langchain/core` here goes through a dynamic
   * `import()` rather than a synchronous `require()` (see
   * `loadLangChainCore`'s docstring for why). Idempotent. Throws/rejects
   * with `InstrumentationError` if `@langchain/core` isn't installed. */
  async instrument(): Promise<void> {
    if (this.handler) return;
    const state = await sharedAdapter();
    const handler = new CostorahLangChainHandler({
      client: this.client,
      calculateCost: this.calculateCostEnabled,
    });
    this.handler = handler;
    state.active = handler;
  }

  async uninstrument(): Promise<void> {
    if (!this.handler) return;
    const state = await sharedAdapter();
    if (state.active === this.handler) state.active = undefined;
    this.handler = undefined;
  }

  isInstrumented(): boolean {
    return this.handler !== undefined;
  }

  get eventsCaptured(): number {
    return this.handler?.eventsCaptured ?? 0;
  }
}
