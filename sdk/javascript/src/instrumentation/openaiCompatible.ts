/**
 * Shared patch logic for every OpenAI-SDK-compatible provider: OpenAI
 * itself, Azure OpenAI, and any provider commonly accessed through
 * `new OpenAI({ baseURL: ... })` (OpenRouter, Ollama, xAI/Grok all
 * publish OpenAI-compatible endpoints and are conventionally used via
 * the official `openai` npm package rather than a bespoke client).
 *
 * All five instrumentors (OpenAIInstrumentor, AzureOpenAIInstrumentor,
 * OpenRouterInstrumentor, OllamaInstrumentor, GrokInstrumentor) patch the
 * exact same two classes — `Completions.prototype.create` and
 * `Responses.prototype.create` from the `openai` package — since that's
 * the single interception point every one of these providers' traffic
 * passes through. To avoid duplicated logic and to avoid one
 * instrumentor's uninstrument() undoing another's patch, the actual
 * monkey-patch is applied once process-wide; each instrumentor's own
 * isInstrumented() still reflects only its own instrument()/
 * uninstrument() calls, and only actively-instrumented providers receive
 * telemetry (see submitForInstrumentors's fixedProvider filter).
 *
 * Provider identity for a given call is determined at call time by
 * inspecting the client's `baseURL` (or its class name for Azure) — the
 * same technique real APM SDKs use for OpenAI-compatible endpoints.
 */

import type { UsageStatus } from "../types.js";
import { BaseInstrumentor, makeExtractedUsage } from "./base.js";
import type { ExtractedUsage } from "./base.js";
import { requireBothTwinsOrThrow } from "./_dualPackage.js";
import { calculateCost } from "./pricing.js";
import { submit } from "./submission.js";

const PROVIDER_HOST_HINTS: [string, string][] = [
  ["openrouter.ai", "openrouter"],
  ["localhost:11434", "ollama"],
  ["127.0.0.1:11434", "ollama"],
  ["api.x.ai", "grok"],
];

function detectProvider(client: unknown): string {
  const className = (client as { constructor?: { name?: string } })?.constructor?.name ?? "";
  if (className === "AzureOpenAI") return "azure_openai";
  const baseUrl = String((client as { baseURL?: string })?.baseURL ?? "");
  for (const [hint, provider] of PROVIDER_HOST_HINTS) {
    if (baseUrl.includes(hint)) return provider;
  }
  return "openai";
}

interface ChatUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  prompt_tokens_details?: { cached_tokens?: number };
}

interface ResponsesUsage {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  input_tokens_details?: { cached_tokens?: number };
}

function extractChatUsage(response: unknown): Record<string, unknown> {
  const usage = (response as { usage?: ChatUsage } | undefined)?.usage;
  if (!usage) return {};
  return {
    inputTokens: usage.prompt_tokens ?? 0,
    outputTokens: usage.completion_tokens ?? 0,
    totalTokens: usage.total_tokens,
    cachedTokens: usage.prompt_tokens_details?.cached_tokens,
  };
}

function extractResponsesUsage(response: unknown): Record<string, unknown> {
  const usage = (response as { usage?: ResponsesUsage } | undefined)?.usage;
  if (!usage) return {};
  return {
    inputTokens: usage.input_tokens ?? 0,
    outputTokens: usage.output_tokens ?? 0,
    totalTokens: usage.total_tokens,
    cachedTokens: usage.input_tokens_details?.cached_tokens,
  };
}

function generateRequestId(): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `sdk_js_instr_${random}`;
}

export abstract class OpenAICompatibleInstrumentor extends BaseInstrumentor {
  /** Every OpenAI-family instrumentor claims exactly one provider slug.
   * The shared patch still detects the real provider per-call, but only
   * submits telemetry for providers with an active, explicitly
   * instrumented family member. */
  abstract readonly fixedProvider: string;

  extractUsage(response: unknown): Record<string, unknown> {
    if (response && typeof response === "object" && "output" in response) {
      return extractResponsesUsage(response);
    }
    return extractChatUsage(response);
  }

  normalize(
    rawUsage: Record<string, unknown>,
    context: { model: string; latencyMs: number; status: UsageStatus; requestId?: string },
  ): ExtractedUsage {
    const inputTokens = Number(rawUsage.inputTokens ?? 0);
    const outputTokens = Number(rawUsage.outputTokens ?? 0);
    const { cost, estimated } = this.calculateCostEnabled
      ? calculateCost(this.fixedProvider, context.model, inputTokens, outputTokens)
      : { cost: 0, estimated: false };

    const metadata: Record<string, unknown> = {};
    if (this.captureMetadata) metadata.costEstimated = estimated;

    return makeExtractedUsage({
      provider: this.fixedProvider,
      model: context.model,
      inputTokens,
      outputTokens,
      cachedTokens: rawUsage.cachedTokens as number | undefined,
      totalTokens: rawUsage.totalTokens as number | undefined,
      cost,
      latencyMs: context.latencyMs,
      status: context.status,
      requestId: context.requestId ?? generateRequestId(),
      metadata,
    });
  }

  protected applyPatches(): void {
    ensureOpenAIPatched(this);
  }

  protected removePatches(): void {
    releaseOpenAIPatch(this);
  }
}

// ── Process-wide shared patch (multiple family members, one physical patch) ─

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type CompletionsCreate = (this: any, ...args: unknown[]) => unknown;

let originals:
  | {
      completions: { proto: Record<string, unknown>; create: CompletionsCreate }[];
      responses: { proto: Record<string, unknown>; create: CompletionsCreate }[];
    }
  | undefined;

const activeInstrumentors: OpenAICompatibleInstrumentor[] = [];

async function submitForInstrumentors(
  provider: string,
  model: string,
  rawUsage: Record<string, unknown>,
  latencyMs: number,
  status: UsageStatus,
): Promise<void> {
  for (const instrumentor of [...activeInstrumentors]) {
    if (instrumentor.fixedProvider !== provider) continue;
    const usage = instrumentor.normalize(rawUsage, { model, latencyMs, status });
    (instrumentor as unknown as { recordCaptured: (n?: number) => void }).recordCaptured?.();
    await submit(usage, instrumentor.getClient());
  }
}

function wrapChatCreate(original: CompletionsCreate): CompletionsCreate {
  return async function (this: { _client: unknown }, ...args: unknown[]) {
    const params = (args[0] ?? {}) as { model?: string; stream?: boolean };
    const provider = detectProvider(this._client);
    const model = params.model ?? "unknown";
    const start = Date.now();
    let result: unknown;
    try {
      result = await original.apply(this, args);
    } catch (err) {
      await submitForInstrumentors(provider, model, {}, Date.now() - start, "error");
      throw err;
    }
    if (params.stream) {
      return wrapChatStream(result as AsyncIterable<unknown>, provider, model, start);
    }
    const raw = extractChatUsage(result);
    await submitForInstrumentors(provider, model, raw, Date.now() - start, "success");
    return result;
  };
}

function wrapResponsesCreate(original: CompletionsCreate): CompletionsCreate {
  return async function (this: { _client: unknown }, ...args: unknown[]) {
    const params = (args[0] ?? {}) as { model?: string };
    const provider = detectProvider(this._client);
    const model = params.model ?? "unknown";
    const start = Date.now();
    let result: unknown;
    try {
      result = await original.apply(this, args);
    } catch (err) {
      await submitForInstrumentors(provider, model, {}, Date.now() - start, "error");
      throw err;
    }
    const raw = extractResponsesUsage(result);
    await submitForInstrumentors(provider, model, raw, Date.now() - start, "success");
    return result;
  };
}

async function* wrapChatStream(
  stream: AsyncIterable<unknown>,
  provider: string,
  model: string,
  start: number,
): AsyncGenerator<unknown, void, undefined> {
  let lastUsage: Record<string, unknown> = {};
  let error: Error | undefined;
  try {
    for await (const chunk of stream) {
      const raw = extractChatUsage(chunk);
      if (Object.keys(raw).length > 0) lastUsage = raw;
      yield chunk;
    }
  } catch (err) {
    error = err instanceof Error ? err : new Error(String(err));
    throw err;
  } finally {
    await submitForInstrumentors(
      provider,
      model,
      lastUsage,
      Date.now() - start,
      error ? "error" : "success",
    );
  }
}

function ensureOpenAIPatched(instrumentor: OpenAICompatibleInstrumentor): void {
  activeInstrumentors.push(instrumentor);
  if (originals) return;

  let completionsProtos: Record<string, unknown>[];
  let responsesProtos: Record<string, unknown>[];
  try {
    completionsProtos = requireBothTwinsOrThrow(
      "openai/resources/chat/completions",
      "Completions",
      "openai",
    );
    responsesProtos = requireBothTwinsOrThrow(
      "openai/resources/responses/responses",
      "Responses",
      "openai",
    );
  } catch (err) {
    activeInstrumentors.pop();
    throw err;
  }

  originals = {
    completions: completionsProtos.map((proto) => ({
      proto,
      create: proto.create as CompletionsCreate,
    })),
    responses: responsesProtos.map((proto) => ({
      proto,
      create: proto.create as CompletionsCreate,
    })),
  };

  for (const { proto, create } of originals.completions) {
    proto.create = wrapChatCreate(create);
  }
  for (const { proto, create } of originals.responses) {
    proto.create = wrapResponsesCreate(create);
  }
}

function releaseOpenAIPatch(instrumentor: OpenAICompatibleInstrumentor): void {
  const index = activeInstrumentors.indexOf(instrumentor);
  if (index !== -1) activeInstrumentors.splice(index, 1);
  if (activeInstrumentors.length > 0) return;
  if (!originals) return;
  for (const { proto, create } of originals.completions) {
    proto.create = create;
  }
  for (const { proto, create } of originals.responses) {
    proto.create = create;
  }
  originals = undefined;
}

// Provider identity resolution and dual-package-hazard-safe patching are
// documented in `_dualPackage.ts`; `openai` ships CJS (`*.js`) and ESM
// (`*.mjs`) twins with independent class objects, so both are patched.

/** Test-only: force-reset shared module state between tests. */
export function resetOpenAIPatchStateForTests(): void {
  originals = undefined;
  activeInstrumentors.length = 0;
}
