/**
 * MistralInstrumentor — automatic usage capture for the official
 * `@mistralai/mistralai` npm package's `chat.complete`/`chat.stream`.
 *
 *     import { Mistral } from "@mistralai/mistralai";
 *     import { MistralInstrumentor } from "@costorah/sdk";
 *
 *     new MistralInstrumentor().instrument();
 *
 *     const client = new Mistral({ apiKey: "..." });
 *     await client.chat.complete({ model: "mistral-large-latest", messages: [] });
 *
 * `@mistralai/mistralai` doesn't export its `Chat` resource class via any
 * public subpath (Node's package.json `exports` field only whitelists a
 * handful of subpaths, none of them `Chat`) — so unlike OpenAI/Anthropic,
 * this instrumentor can't `require()` the class directly. It reaches the
 * same shared prototype another way: `chat.complete`/`chat.stream` are
 * defined on `Chat.prototype`, which is identical across every `Mistral`
 * client instance. Constructing one throwaway `Mistral` client (no
 * network call — the constructor just wires config) yields a real
 * reference to the same shared prototype every future client uses, so
 * patching it once still intercepts calls made by clients the caller
 * constructs independently afterward.
 */

import { createRequire } from "node:module";

import type { UsageStatus } from "../types.js";
import { BaseInstrumentor, InstrumentationError, makeExtractedUsage } from "./base.js";
import type { ExtractedUsage } from "./base.js";
import { calculateCost } from "./pricing.js";
import { instrumentedAsyncStream } from "./streaming.js";
import { submit } from "./submission.js";

const nodeRequire = createRequire(import.meta.url);

interface MistralUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
}

function extract(response: unknown): Record<string, unknown> {
  const usage = (response as { usage?: MistralUsage } | undefined)?.usage;
  if (!usage) return {};
  return {
    inputTokens: usage.prompt_tokens ?? 0,
    outputTokens: usage.completion_tokens ?? 0,
    totalTokens: usage.total_tokens,
  };
}

function aggregateStream(events: unknown[]): Record<string, unknown> {
  for (let i = events.length - 1; i >= 0; i--) {
    const chunk = (events[i] as { data?: unknown }).data;
    const raw = chunk ? extract(chunk) : {};
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
type ChatMethod = (this: any, ...args: unknown[]) => unknown;

export class MistralInstrumentor extends BaseInstrumentor {
  readonly name = "mistral";

  private originalComplete: ChatMethod | undefined;
  private originalStream: ChatMethod | undefined;
  private chatProto: Record<string, unknown> | undefined;

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
      ? calculateCost("mistral", context.model, inputTokens, outputTokens)
      : { cost: 0, estimated: false };
    const metadata: Record<string, unknown> = {};
    if (this.captureMetadata) metadata.costEstimated = estimated;

    return makeExtractedUsage({
      provider: "mistral",
      model: context.model,
      inputTokens,
      outputTokens,
      totalTokens: rawUsage.totalTokens as number | undefined,
      cost,
      latencyMs: context.latencyMs,
      status: context.status,
      requestId: context.requestId ?? generateRequestId(),
      metadata,
    });
  }

  protected applyPatches(): void {
    let MistralClient: new (opts: { apiKey: string }) => { chat: object };
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const mod: any = nodeRequire("@mistralai/mistralai");
      MistralClient = mod.Mistral;
      if (!MistralClient) throw new Error("Mistral export not found");
    } catch (err) {
      throw new InstrumentationError(
        "The '@mistralai/mistralai' package is not installed. Install it with " +
          "`npm install @mistralai/mistralai` to use this instrumentor.",
      );
    }

    const probe = new MistralClient({ apiKey: "costorah-instrumentation-probe" });
    const chatProto = Object.getPrototypeOf(probe.chat) as Record<string, unknown>;
    this.chatProto = chatProto;
    this.originalComplete = chatProto.complete as ChatMethod;
    this.originalStream = chatProto.stream as ChatMethod;

    chatProto.complete = this.wrapComplete(this.originalComplete);
    chatProto.stream = this.wrapStream(this.originalStream);
  }

  protected removePatches(): void {
    if (!this.chatProto) return;
    if (this.originalComplete) this.chatProto.complete = this.originalComplete;
    if (this.originalStream) this.chatProto.stream = this.originalStream;
    this.chatProto = undefined;
    this.originalComplete = undefined;
    this.originalStream = undefined;
  }

  private async submitResult(
    model: string,
    raw: Record<string, unknown>,
    latencyMs: number,
    status: UsageStatus,
  ): Promise<void> {
    const usage = this.normalize(raw, { model, latencyMs, status });
    this.recordCaptured();
    await submit(usage);
  }

  private wrapComplete(original: ChatMethod): ChatMethod {
    const submitResult = this.submitResult.bind(this);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return async function (this: any, ...args: unknown[]) {
      const params = (args[0] ?? {}) as { model?: string };
      const model = params.model ?? "unknown";
      const start = Date.now();
      let result: unknown;
      try {
        result = await original.apply(this, args);
      } catch (err) {
        await submitResult(model, {}, Date.now() - start, "error");
        throw err;
      }
      await submitResult(model, extract(result), Date.now() - start, "success");
      return result;
    };
  }

  private wrapStream(original: ChatMethod): ChatMethod {
    const submitResult = this.submitResult.bind(this);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return async function (this: any, ...args: unknown[]) {
      const params = (args[0] ?? {}) as { model?: string };
      const model = params.model ?? "unknown";
      const start = Date.now();
      const result = await original.apply(this, args);
      return instrumentedAsyncStream(
        result as AsyncIterable<unknown>,
        start,
        async (chunks, elapsedMs, error) => {
          const raw = aggregateStream(chunks);
          await submitResult(model, raw, elapsedMs, error ? "error" : "success");
        },
      );
    };
  }
}
