/**
 * VercelAIInstrumentor — automatic usage capture for the Vercel AI SDK
 * (`ai` npm package, v5's `LanguageModelV2` middleware architecture).
 *
 *     import { openai } from "@ai-sdk/openai";
 *     import { streamText } from "ai";
 *     import { VercelAIInstrumentor } from "@costorah/sdk";
 *
 *     const instrumentor = new VercelAIInstrumentor();
 *     instrumentor.instrument();
 *
 *     const model = instrumentor.wrapModel(openai("gpt-4o-mini"));
 *     await streamText({ model, prompt: "Hello" });   // usage, cost,
 *                                                       // latency, and
 *                                                       // finish reason
 *                                                       // are captured
 *                                                       // automatically
 *
 * ## Why every call site still needs `wrapModel()`, unlike the OpenAI/
 * Anthropic/etc. instrumentors
 *
 * The provider instrumentors in this package (`OpenAIInstrumentor`,
 * `AnthropicInstrumentor`, ...) patch a shared class's prototype method
 * (e.g. `Completions.prototype.create`) once, process-wide — every
 * client instance and every call site is covered automatically after a
 * single `instrument()` call, with zero code changes at any call site.
 *
 * The Vercel AI SDK has no equivalent global interception point to patch.
 * `@ai-sdk/openai`'s `openai("gpt-4o-mini")` (and every other provider
 * package's model factory) returns a fresh, independent `LanguageModelV2`
 * plain object per call — there is no shared prototype method or module-
 * level function binding that every model instance routes through, and
 * the `ai` package's own top-level functions (`generateText`,
 * `streamText`, ...) are plain ESM named exports, not patchable from
 * outside the module (ESM module namespace objects are read-only
 * bindings). This was verified by inspecting the installed `ai`
 * (v5.0.210) and `@ai-sdk/openai` (v2.0.110) packages' actual type
 * definitions and runtime shape, not assumed.
 *
 * The AI SDK's own documented, official extension point for exactly this
 * use case is `wrapLanguageModel({ model, middleware })` — the same
 * mechanism the AI SDK's own built-in middleware
 * (`extractReasoningMiddleware`, `simulateStreamingMiddleware`) uses.
 * `VercelAIInstrumentor.wrapModel(model)` is a thin, one-line convenience
 * around exactly that. This is a one-time setup step at model-creation
 * (analogous to `instrument()` itself), not a "manual tracking call" at
 * every request — no code at any `generateText`/`streamText` call site
 * changes.
 */

import { randomUUID } from "node:crypto";

import { getRequestContext, runWithRequestContext } from "../context.js";
import { calculateCost } from "./pricing.js";
import { submit } from "./submission.js";
import type { ExtractedUsage } from "./base.js";
import type { Costorah } from "../client.js";
import type { UsageStatus } from "../types.js";

/** Structural subset of `@ai-sdk/provider`'s `LanguageModelV2` this
 * instrumentor needs. Declared locally (not imported from `@ai-sdk/
 * provider`) so this module has no hard dependency on the `ai`/
 * `@ai-sdk/*` packages being installed at all — only users who actually
 * call `wrapModel()` need them present. */
export interface VercelLanguageModel {
  readonly specificationVersion?: string;
  readonly provider: string;
  readonly modelId: string;
}

interface UsageLike {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  reasoningTokens?: number;
  cachedInputTokens?: number;
}

interface GenerateResultLike {
  usage?: UsageLike | undefined;
  finishReason?: string | undefined;
}

export interface VercelLanguageModelMiddleware {
  middlewareVersion?: "v2";
  wrapGenerate?: (options: {
    doGenerate: () => Promise<GenerateResultLike>;
    doStream: () => Promise<unknown>;
    params: unknown;
    model: VercelLanguageModel;
  }) => Promise<GenerateResultLike>;
  wrapStream?: (options: {
    doGenerate: () => Promise<unknown>;
    doStream: () => Promise<{ stream: ReadableStream<unknown> }>;
    params: unknown;
    model: VercelLanguageModel;
  }) => Promise<{ stream: ReadableStream<unknown> }>;
}

const _MODULE_PREFIX_TO_PROVIDER: Record<string, string> = {
  openai: "openai",
  anthropic: "anthropic",
  google: "google",
  "google-vertex": "google",
  mistral: "mistral",
  cohere: "cohere",
  azure: "azure_openai",
  bedrock: "bedrock",
  amazon: "bedrock",
  groq: "grok",
  xai: "grok",
};

/** Vercel AI SDK provider IDs look like "openai.responses",
 * "anthropic.messages", "google.generative-ai" — the part before the
 * first "." is the base provider. */
export function inferProviderFromVercelProviderId(providerId: string): string | undefined {
  const base = providerId.split(".")[0]?.toLowerCase();
  if (!base) return undefined;
  return _MODULE_PREFIX_TO_PROVIDER[base];
}

export interface VercelAIInstrumentorOptions {
  client?: Costorah;
  calculateCost?: boolean;
}

function requestId(): string {
  return `sdk_js_vercel_ai_${randomUUID().replace(/-/g, "")}`;
}

export class VercelAIInstrumentor {
  private readonly client: Costorah | undefined;
  private readonly calculateCostEnabled: boolean;
  private instrumented = false;
  private eventsCapturedTotal = 0;

  constructor(options: VercelAIInstrumentorOptions = {}) {
    this.client = options.client;
    this.calculateCostEnabled = options.calculateCost ?? true;
  }

  /** No global patching happens here — see the module docstring for
   * why the AI SDK has no equivalent interception point. instrument()
   * simply arms this instance so wrapModel() starts producing telemetry;
   * calling wrapModel() before instrument() is a no-op passthrough
   * (returns the original model unwrapped). */
  instrument(): void {
    this.instrumented = true;
  }

  uninstrument(): void {
    this.instrumented = false;
  }

  isInstrumented(): boolean {
    return this.instrumented;
  }

  get eventsCaptured(): number {
    return this.eventsCapturedTotal;
  }

  /** Returns `model` wrapped with COSTORAH's telemetry middleware, or
   * `model` unchanged if `instrument()` hasn't been called. Intended to
   * be called once per model instance, at construction time. */
  wrapModel<M extends VercelLanguageModel>(model: M): M {
    if (!this.instrumented) return model;
    const middleware = this.middleware();
    return wrapLanguageModelStructurally(model, middleware);
  }

  /** The raw `LanguageModelV2Middleware`-shaped object, for callers who
   * want to pass it directly to the real `wrapLanguageModel` from `ai`
   * (e.g. to compose with other middleware) instead of using
   * `wrapModel()`. */
  middleware(): VercelLanguageModelMiddleware {
    const submitUsage = this.submitUsage.bind(this);
    const recordCaptured = () => {
      this.eventsCapturedTotal += 1;
    };

    return {
      middlewareVersion: "v2",
      wrapGenerate: async ({ doGenerate, model }) => {
        const start = Date.now();
        const id = requestId();
        const cm = model.modelId
          ? runWithVercelToolContext(model.modelId)
          : (fn: () => Promise<GenerateResultLike>) => fn();
        let result: GenerateResultLike;
        let status: UsageStatus = "success";
        try {
          result = await cm(doGenerate);
        } catch (error) {
          status = "error";
          recordCaptured();
          throw error;
        }
        const latencyMs = Date.now() - start;
        recordCaptured();
        // Awaited (not fire-and-forget) so a `client.flush()` called
        // right after the caller's `generateText(...)` resolves
        // reliably has the event already enqueued — matches every
        // other instrumentor's `await submit(...)` pattern.
        await submitUsage(model, result, { latencyMs, status, requestId: id });
        return result;
      },
      wrapStream: async ({ doStream, model }) => {
        const start = Date.now();
        const id = requestId();
        const result = await doStream();
        recordCaptured();
        // Fire-and-forget here (unlike wrapGenerate above) is
        // unavoidable: the finish/usage part only arrives once the
        // caller has fully drained `result.stream`, which happens after
        // `wrapStream` itself has already returned — there is no later
        // point in this function's own control flow left to await.
        const usageCapturingStream = captureUsageFromStream(
          result.stream,
          (usage, finishReason) => {
            const latencyMs = Date.now() - start;
            void submitUsage(
              model,
              { usage, finishReason },
              { latencyMs, status: "success", requestId: id },
            );
          },
        );
        return { stream: usageCapturingStream };
      },
    };
  }

  private async submitUsage(
    model: VercelLanguageModel,
    result: GenerateResultLike,
    context: { latencyMs: number; status: UsageStatus; requestId: string },
  ): Promise<void> {
    const provider = inferProviderFromVercelProviderId(model.provider);
    if (!provider) return;
    const usage = result.usage;
    if (!usage) return;

    const inputTokens = usage.inputTokens ?? 0;
    const outputTokens = usage.outputTokens ?? 0;
    const { cost, estimated } = this.calculateCostEnabled
      ? calculateCost(provider, model.modelId, inputTokens, outputTokens)
      : { cost: 0, estimated: false };

    const metadata: Record<string, unknown> = {
      framework: "vercel-ai-sdk",
      costEstimated: estimated,
    };
    if (result.finishReason) metadata.finishReason = result.finishReason;
    if (usage.reasoningTokens !== undefined) metadata.reasoningTokens = usage.reasoningTokens;
    if (usage.cachedInputTokens !== undefined) metadata.cachedTokens = usage.cachedInputTokens;
    const requestContext = getRequestContext();
    if (requestContext) metadata.requestContext = requestContext;

    const extracted: ExtractedUsage = {
      provider,
      model: model.modelId,
      inputTokens,
      outputTokens,
      cachedTokens: usage.cachedInputTokens,
      totalTokens: usage.totalTokens,
      cost,
      currency: "USD",
      latencyMs: context.latencyMs,
      status: context.status,
      requestId: context.requestId,
      timestamp: new Date(),
      metadata,
    };

    await submit(extracted, this.client);
  }
}

function runWithVercelToolContext(modelId: string) {
  return <T>(fn: () => Promise<T>): Promise<T> =>
    runWithRequestContext({ ...(getRequestContext() ?? {}), vercelAiModelId: modelId }, fn);
}

/** Wraps `model` with `middleware`'s `wrapGenerate`/`wrapStream`, using
 * only the structural shape this module needs — a minimal local
 * reimplementation of what `ai`'s real `wrapLanguageModel` does for
 * exactly these two hooks, so this module has no hard dependency on the
 * `ai` package. Callers who need the full `wrapLanguageModel` behavior
 * (transformParams, overrideProvider, etc.) should call the real one
 * from `ai` directly, passing `instrumentor.middleware()`. */
function wrapLanguageModelStructurally<M extends VercelLanguageModel>(
  model: M,
  middleware: VercelLanguageModelMiddleware,
): M {
  const target = model as unknown as {
    doGenerate?: (...args: unknown[]) => Promise<GenerateResultLike>;
    doStream?: (...args: unknown[]) => Promise<{ stream: ReadableStream<unknown> }>;
  };
  const originalDoGenerate = target.doGenerate?.bind(target);
  const originalDoStream = target.doStream?.bind(target);

  const wrapped = Object.create(model as object) as M & {
    doGenerate?: (...args: unknown[]) => Promise<GenerateResultLike>;
    doStream?: (...args: unknown[]) => Promise<{ stream: ReadableStream<unknown> }>;
  };

  if (originalDoGenerate && middleware.wrapGenerate) {
    wrapped.doGenerate = (...args: unknown[]) =>
      middleware.wrapGenerate!({
        doGenerate: () => originalDoGenerate(...args),
        doStream: () =>
          originalDoStream ? originalDoStream(...args) : Promise.reject(new Error("no doStream")),
        params: args[0],
        model,
      });
  }
  if (originalDoStream && middleware.wrapStream) {
    wrapped.doStream = (...args: unknown[]) =>
      middleware.wrapStream!({
        doGenerate: () =>
          originalDoGenerate
            ? originalDoGenerate(...args)
            : Promise.reject(new Error("no doGenerate")),
        doStream: () => originalDoStream(...args),
        params: args[0],
        model,
      });
  }

  return wrapped;
}

/** Reads usage/finishReason off the terminal stream part (AI SDK v2
 * stream protocol's `finish` part carries both) without buffering or
 * inspecting any text/tool-call content — passes every chunk through
 * unmodified and untouched. */
function captureUsageFromStream(
  stream: ReadableStream<unknown>,
  onFinish: (usage: UsageLike | undefined, finishReason: string | undefined) => void,
): ReadableStream<unknown> {
  const reader = stream.getReader();
  return new ReadableStream({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        controller.close();
        return;
      }
      const part = value as { type?: string; usage?: UsageLike; finishReason?: string };
      if (part?.type === "finish") {
        onFinish(part.usage, part.finishReason);
      }
      controller.enqueue(value);
    },
    cancel(reason) {
      return reader.cancel(reason);
    },
  });
}
