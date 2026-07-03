/**
 * GeminiInstrumentor — automatic usage capture for the official
 * `@google/genai` npm package's `models.generateContent`/
 * `generateContentStream`.
 *
 *     import { GoogleGenAI } from "@google/genai";
 *     import { GeminiInstrumentor } from "@costorah/sdk";
 *
 *     const client = new GoogleGenAI({ apiKey: "..." });
 *     new GeminiInstrumentor().instrument(client);
 *
 *     await client.models.generateContent({ model: "gemini-1.5-pro", contents: "Hello" });
 *
 * Unlike every other JS provider here, `@google/genai`'s `Models` class
 * declares `generateContent`/`generateContentStream` as instance-level
 * arrow-function class fields, not prototype methods — confirmed both via
 * the package's `.d.ts` (`generateContent: (params) => Promise<...>`,
 * backed by a private `generateContentInternal`) and empirically
 * (`Object.prototype.hasOwnProperty.call(client.models, "generateContent")
 * === true`, and the property is absent from `Models.prototype`). There is
 * therefore no shared prototype to patch once process-wide the way
 * OpenAI/Anthropic/Mistral/Bedrock allow — this instrumentor requires the
 * specific client instance to wrap, via `instrument(client)` instead of a
 * zero-arg `instrument()`.
 */

import type { UsageStatus } from "../types.js";
import { BaseInstrumentor, InstrumentationError, makeExtractedUsage } from "./base.js";
import type { ExtractedUsage } from "./base.js";
import { calculateCost } from "./pricing.js";
import { instrumentedAsyncStream } from "./streaming.js";
import { submit } from "./submission.js";

interface GeminiUsageMetadata {
  promptTokenCount?: number;
  candidatesTokenCount?: number;
  cachedContentTokenCount?: number;
  totalTokenCount?: number;
}

function extract(response: unknown): Record<string, unknown> {
  const usage = (response as { usageMetadata?: GeminiUsageMetadata } | undefined)?.usageMetadata;
  if (!usage) return {};
  return {
    inputTokens: usage.promptTokenCount ?? 0,
    outputTokens: usage.candidatesTokenCount ?? 0,
    cachedTokens: usage.cachedContentTokenCount,
    totalTokens: usage.totalTokenCount,
  };
}

/** Each streamed chunk's usageMetadata already reflects running totals —
 * the last chunk with usage info carries the final counts. */
function aggregateStream(chunks: unknown[]): Record<string, unknown> {
  for (let i = chunks.length - 1; i >= 0; i--) {
    const raw = extract(chunks[i]);
    if (Object.keys(raw).length > 0) return raw;
  }
  return {};
}

function generateRequestId(): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `sdk_js_instr_${random}`;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type GenerateContentMethod = (...args: any[]) => unknown;

interface GeminiClient {
  models: {
    generateContent: GenerateContentMethod;
    generateContentStream: GenerateContentMethod;
  };
}

export class GeminiInstrumentor extends BaseInstrumentor {
  readonly name = "google";

  private target: GeminiClient | undefined;
  private originalGenerateContent: GenerateContentMethod | undefined;
  private originalGenerateContentStream: GenerateContentMethod | undefined;

  extractUsage(response: unknown): Record<string, unknown> {
    return extract(response);
  }

  normalize(
    rawUsage: Record<string, unknown>,
    context: { model: string; latencyMs: number; status: UsageStatus; requestId?: string },
  ): ExtractedUsage {
    const inputTokens = Number(rawUsage.inputTokens ?? 0);
    const outputTokens = Number(rawUsage.outputTokens ?? 0);
    const { cost, estimated } = this.calculateCostEnabled
      ? calculateCost("google", context.model, inputTokens, outputTokens)
      : { cost: 0, estimated: false };
    const metadata: Record<string, unknown> = {};
    if (this.captureMetadata) metadata.costEstimated = estimated;

    return makeExtractedUsage({
      provider: "google",
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

  /** GeminiInstrumentor cannot patch a shared prototype (see module
   * docstring) — pass the specific `GoogleGenAI` client instance to wrap. */
  instrument(client?: GeminiClient): void {
    if (!this.enabled) return;
    if (this.isInstrumented()) return;
    if (!client?.models || typeof client.models.generateContent !== "function") {
      throw new InstrumentationError(
        "GeminiInstrumentor.instrument(client) requires a GoogleGenAI client instance " +
          "(with a `.models` resource) — call `new GeminiInstrumentor().instrument(client)`.",
      );
    }
    this.target = client;
    this.originalGenerateContent = client.models.generateContent.bind(client.models);
    this.originalGenerateContentStream = client.models.generateContentStream.bind(client.models);
    client.models.generateContent = this.wrap(this.originalGenerateContent, false);
    client.models.generateContentStream = this.wrap(this.originalGenerateContentStream, true);
    this.markInstrumented();
  }

  uninstrument(): void {
    if (!this.isInstrumented()) return;
    if (this.target && this.originalGenerateContent && this.originalGenerateContentStream) {
      this.target.models.generateContent = this.originalGenerateContent;
      this.target.models.generateContentStream = this.originalGenerateContentStream;
    }
    this.target = undefined;
    this.originalGenerateContent = undefined;
    this.originalGenerateContentStream = undefined;
    this.markUninstrumented();
  }

  protected applyPatches(): void {
    throw new InstrumentationError(
      "GeminiInstrumentor requires a client instance: call instrument(client), not instrument().",
    );
  }

  protected removePatches(): void {
    // Unused: uninstrument() is fully overridden above.
  }

  private wrap(original: GenerateContentMethod, stream: boolean): GenerateContentMethod {
    const normalize = this.normalize.bind(this);
    const recordCaptured = this.recordCaptured.bind(this);

    const submitResult = async (
      model: string,
      raw: Record<string, unknown>,
      latencyMs: number,
      status: UsageStatus,
    ): Promise<void> => {
      const usage = normalize(raw, { model, latencyMs, status });
      recordCaptured();
      await submit(usage);
    };

    return async (...args: unknown[]) => {
      const params = (args[0] ?? {}) as { model?: string };
      const model = params.model ?? "unknown";
      const start = Date.now();
      let result: unknown;
      try {
        result = await original(...args);
      } catch (err) {
        await submitResult(model, {}, Date.now() - start, "error");
        throw err;
      }
      if (stream) {
        return instrumentedAsyncStream(
          result as AsyncIterable<unknown>,
          start,
          async (chunks, elapsedMs, error) => {
            const raw = aggregateStream(chunks);
            await submitResult(model, raw, elapsedMs, error ? "error" : "success");
          },
        );
      }
      const raw = extract(result);
      await submitResult(model, raw, Date.now() - start, "success");
      return result;
    };
  }
}
