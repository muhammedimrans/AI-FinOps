/**
 * CohereInstrumentor — automatic usage capture for the official
 * `cohere-ai` npm package's `chat`/`chatStream`.
 *
 *     import { CohereClientV2 } from "cohere-ai";
 *     import { CohereInstrumentor } from "@costorah/sdk";
 *
 *     const client = new CohereClientV2({ token: "..." });
 *     new CohereInstrumentor().instrument(client);
 *
 *     await client.chat({ model: "command-r-plus", messages: [] });
 *
 * Like `@google/genai`, `cohere-ai`'s `CohereClientV2.chat`/`chatStream`
 * are own-instance bound-function properties (confirmed via
 * `Object.getOwnPropertyDescriptor(client, "chat")` showing
 * `{ value: [Function: bound chat], writable: true, configurable: true }`
 * directly on the instance), not prototype methods — there is no shared
 * prototype to patch once process-wide. This instrumentor requires the
 * specific client instance to wrap, via `instrument(client)` instead of a
 * zero-arg `instrument()`.
 */

import type { UsageStatus } from "../types.js";
import { BaseInstrumentor, InstrumentationError, makeExtractedUsage } from "./base.js";
import type { ExtractedUsage } from "./base.js";
import { calculateCost } from "./pricing.js";
import { instrumentedAsyncStream } from "./streaming.js";
import { submit } from "./submission.js";

interface CohereUsage {
  tokens?: { inputTokens?: number; outputTokens?: number };
}

function extract(response: unknown): Record<string, unknown> {
  const usage = (response as { usage?: CohereUsage } | undefined)?.usage;
  const tokens = usage?.tokens;
  if (!tokens) return {};
  return {
    inputTokens: tokens.inputTokens ?? 0,
    outputTokens: tokens.outputTokens ?? 0,
  };
}

/** The terminal "message-end" stream event carries the final response
 * (and usage) — walk backwards from the end to find it. */
function aggregateStream(events: unknown[]): Record<string, unknown> {
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i];
    const response = (event as { response?: unknown })?.response;
    const raw = response !== undefined ? extract(response) : extract(event);
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
type ChatMethod = (...args: any[]) => unknown;

interface CohereClient {
  chat: ChatMethod;
  chatStream: ChatMethod;
}

export class CohereInstrumentor extends BaseInstrumentor {
  readonly name = "cohere";

  private target: CohereClient | undefined;
  private originalChat: ChatMethod | undefined;
  private originalChatStream: ChatMethod | undefined;

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
      ? calculateCost("cohere", context.model, inputTokens, outputTokens)
      : { cost: 0, estimated: false };
    const metadata: Record<string, unknown> = {};
    if (this.captureMetadata) metadata.costEstimated = estimated;

    return makeExtractedUsage({
      provider: "cohere",
      model: context.model,
      inputTokens,
      outputTokens,
      cost,
      latencyMs: context.latencyMs,
      status: context.status,
      requestId: context.requestId ?? generateRequestId(),
      metadata,
    });
  }

  /** CohereInstrumentor cannot patch a shared prototype (see module
   * docstring) — pass the specific `CohereClientV2` instance to wrap. */
  instrument(client?: CohereClient): void {
    if (!this.enabled) return;
    if (this.isInstrumented()) return;
    if (!client || typeof client.chat !== "function") {
      throw new InstrumentationError(
        "CohereInstrumentor.instrument(client) requires a CohereClientV2 instance — " +
          "call `new CohereInstrumentor().instrument(client)`.",
      );
    }
    this.target = client;
    this.originalChat = client.chat.bind(client);
    this.originalChatStream = client.chatStream.bind(client);
    client.chat = this.wrapChat(this.originalChat);
    client.chatStream = this.wrapChatStream(this.originalChatStream);
    this.markInstrumented();
  }

  uninstrument(): void {
    if (!this.isInstrumented()) return;
    if (this.target && this.originalChat && this.originalChatStream) {
      this.target.chat = this.originalChat;
      this.target.chatStream = this.originalChatStream;
    }
    this.target = undefined;
    this.originalChat = undefined;
    this.originalChatStream = undefined;
    this.markUninstrumented();
  }

  protected applyPatches(): void {
    throw new InstrumentationError(
      "CohereInstrumentor requires a client instance: call instrument(client), not instrument().",
    );
  }

  protected removePatches(): void {
    // Unused: uninstrument() is fully overridden above.
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

  private wrapChat(original: ChatMethod): ChatMethod {
    return async (...args: unknown[]) => {
      const params = (args[0] ?? {}) as { model?: string };
      const model = params.model ?? "unknown";
      const start = Date.now();
      let result: unknown;
      try {
        result = await original(...args);
      } catch (err) {
        await this.submitResult(model, {}, Date.now() - start, "error");
        throw err;
      }
      await this.submitResult(model, extract(result), Date.now() - start, "success");
      return result;
    };
  }

  private wrapChatStream(original: ChatMethod): ChatMethod {
    return async (...args: unknown[]) => {
      const params = (args[0] ?? {}) as { model?: string };
      const model = params.model ?? "unknown";
      const start = Date.now();
      const result = await original(...args);
      return instrumentedAsyncStream(
        result as AsyncIterable<unknown>,
        start,
        async (chunks, elapsedMs, error) => {
          const raw = aggregateStream(chunks);
          await this.submitResult(model, raw, elapsedMs, error ? "error" : "success");
        },
      );
    };
  }
}
