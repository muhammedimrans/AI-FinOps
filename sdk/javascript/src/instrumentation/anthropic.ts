/**
 * AnthropicInstrumentor — automatic usage capture for the official
 * `@anthropic-ai/sdk` npm package's Messages API (non-streaming and
 * streaming).
 *
 *     import Anthropic from "@anthropic-ai/sdk";
 *     import { AnthropicInstrumentor } from "@costorah/sdk";
 *
 *     new AnthropicInstrumentor().instrument();
 *
 *     const client = new Anthropic();
 *     await client.messages.create({ model: "claude-sonnet-4", max_tokens: 1024, messages: [] });
 */

import type { UsageStatus } from "../types.js";
import { BaseInstrumentor, makeExtractedUsage } from "./base.js";
import type { ExtractedUsage } from "./base.js";
import { requireBothTwinsOrThrow } from "./_dualPackage.js";
import { calculateCost } from "./pricing.js";
import { instrumentedAsyncStream } from "./streaming.js";
import { submit } from "./submission.js";

interface AnthropicUsage {
  input_tokens?: number;
  output_tokens?: number;
  cache_read_input_tokens?: number;
}

function extract(response: unknown): Record<string, unknown> {
  const usage = (response as { usage?: AnthropicUsage } | undefined)?.usage;
  if (!usage) return {};
  return {
    inputTokens: usage.input_tokens ?? 0,
    outputTokens: usage.output_tokens ?? 0,
    cachedTokens: usage.cache_read_input_tokens,
  };
}

/** Anthropic streams a `message_start` event (input_tokens, output_tokens
 * = 0) then `message_delta` events whose `usage` carries the running
 * output token count — the last event with usage info has the final
 * totals. */
function aggregateStream(events: unknown[]): Record<string, unknown> {
  const raw: Record<string, unknown> = {};
  for (const event of events) {
    const usage =
      (event as { usage?: AnthropicUsage }).usage ??
      (event as { message?: { usage?: AnthropicUsage } }).message?.usage;
    if (!usage) continue;
    if (usage.input_tokens !== undefined) raw.inputTokens = usage.input_tokens;
    if (usage.output_tokens !== undefined) raw.outputTokens = usage.output_tokens;
    if (usage.cache_read_input_tokens !== undefined) {
      raw.cachedTokens = usage.cache_read_input_tokens;
    }
  }
  return raw;
}

function generateRequestId(): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `sdk_js_instr_${random}`;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type MessagesCreate = (this: any, ...args: unknown[]) => unknown;

export class AnthropicInstrumentor extends BaseInstrumentor {
  readonly name = "anthropic";

  private originals: { proto: Record<string, unknown>; create: MessagesCreate }[] | undefined;

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
      ? calculateCost("anthropic", context.model, inputTokens, outputTokens)
      : { cost: 0, estimated: false };
    const metadata: Record<string, unknown> = {};
    if (this.captureMetadata) metadata.costEstimated = estimated;

    return makeExtractedUsage({
      provider: "anthropic",
      model: context.model,
      inputTokens,
      outputTokens,
      cachedTokens: rawUsage.cachedTokens as number | undefined,
      cost,
      latencyMs: context.latencyMs,
      status: context.status,
      requestId: context.requestId ?? generateRequestId(),
      metadata,
    });
  }

  protected applyPatches(): void {
    const protos = requireBothTwinsOrThrow(
      "@anthropic-ai/sdk/resources/messages",
      "Messages",
      "@anthropic-ai/sdk",
    );
    this.originals = protos.map((proto) => ({ proto, create: proto.create as MessagesCreate }));
    for (const { proto, create } of this.originals) {
      proto.create = this.wrap(create);
    }
  }

  protected removePatches(): void {
    if (!this.originals) return;
    for (const { proto, create } of this.originals) {
      proto.create = create;
    }
    this.originals = undefined;
  }

  private wrap(original: MessagesCreate): MessagesCreate {
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

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return async function (this: any, ...args: unknown[]) {
      const params = (args[0] ?? {}) as { model?: string; stream?: boolean };
      const model = params.model ?? "unknown";
      const start = Date.now();
      let result: unknown;
      try {
        result = await original.apply(this, args);
      } catch (err) {
        await submitResult(model, {}, Date.now() - start, "error");
        throw err;
      }
      if (params.stream) {
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
