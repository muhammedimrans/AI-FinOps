/**
 * BedrockInstrumentor — automatic usage capture for Amazon Bedrock's
 * unified Converse API (`ConverseCommand`/`ConverseStreamCommand`),
 * reached through the official `@aws-sdk/client-bedrock-runtime` package.
 *
 *     import { BedrockRuntimeClient, ConverseCommand } from "@aws-sdk/client-bedrock-runtime";
 *     import { BedrockInstrumentor } from "@costorah/sdk";
 *
 *     new BedrockInstrumentor().instrument();
 *
 *     const client = new BedrockRuntimeClient({ region: "us-east-1" });
 *     await client.send(new ConverseCommand({ modelId: "...", messages: [] }));
 *
 * Unlike Python's boto3 (whose service clients are generated dynamically
 * per instance, with no fixed class to patch), the JS AWS SDK v3's
 * `BedrockRuntimeClient` is a real, stable class whose `send()` method is
 * inherited from a shared base `Client.prototype` (from
 * `@smithy/smithy-client`) — genuinely prototype-patchable like every
 * other provider here. Verified empirically that the ESM and CJS entry
 * points of `@aws-sdk/client-bedrock-runtime` resolve to the *same*
 * underlying `Client.prototype` object, so (unlike `openai` and
 * `@anthropic-ai/sdk`) there is no dual-package hazard to guard against
 * for this package.
 *
 * `send()` is generic — it accepts any Bedrock Runtime command, not just
 * Converse. This instrumentor only intercepts `ConverseCommand` and
 * `ConverseStreamCommand` (identified by `command.constructor.name`);
 * every other command passes straight through untouched. The Converse
 * API returns a standardized `usage` object regardless of the underlying
 * model provider (Anthropic, Titan, Llama, Mistral, ...); the older
 * `invoke_model`/`InvokeModelCommand` returns raw, per-model-family JSON
 * that would need a separate parser per model family to normalize
 * honestly, which is out of scope for this phase — see
 * docs/TROUBLESHOOTING_INSTRUMENTATION.md.
 */

import { createRequire } from "node:module";

import type { UsageStatus } from "../types.js";
import { BaseInstrumentor, InstrumentationError, makeExtractedUsage } from "./base.js";
import type { ExtractedUsage } from "./base.js";
import { calculateCost } from "./pricing.js";
import { submit } from "./submission.js";

const nodeRequire = createRequire(import.meta.url);

interface BedrockUsage {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
}

function extract(response: unknown): Record<string, unknown> {
  const usage = (response as { usage?: BedrockUsage } | undefined)?.usage;
  if (!usage) return {};
  return {
    inputTokens: usage.inputTokens ?? 0,
    outputTokens: usage.outputTokens ?? 0,
    totalTokens: usage.totalTokens,
  };
}

function generateRequestId(): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `sdk_js_instr_${random}`;
}

const CONVERSE_COMMANDS = new Set(["ConverseCommand", "ConverseStreamCommand"]);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SendMethod = (this: any, ...args: unknown[]) => unknown;

export class BedrockInstrumentor extends BaseInstrumentor {
  readonly name = "bedrock";

  private proto: Record<string, unknown> | undefined;
  private originalSend: SendMethod | undefined;

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
      ? calculateCost("bedrock", context.model, inputTokens, outputTokens)
      : { cost: 0, estimated: false };
    const metadata: Record<string, unknown> = {};
    if (this.captureMetadata) metadata.costEstimated = estimated;

    return makeExtractedUsage({
      provider: "bedrock",
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
    let BedrockRuntimeClient: { prototype: Record<string, unknown> };
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const mod: any = nodeRequire("@aws-sdk/client-bedrock-runtime");
      BedrockRuntimeClient = mod.BedrockRuntimeClient;
      if (!BedrockRuntimeClient) throw new Error("BedrockRuntimeClient export not found");
    } catch {
      throw new InstrumentationError(
        "The '@aws-sdk/client-bedrock-runtime' package is not installed. Install it with " +
          "`npm install @aws-sdk/client-bedrock-runtime` to use this instrumentor.",
      );
    }

    // `send()` lives on the shared base Client.prototype, one level up
    // from BedrockRuntimeClient.prototype itself.
    const proto = Object.getPrototypeOf(BedrockRuntimeClient.prototype) as Record<
      string,
      unknown
    >;
    this.proto = proto;
    this.originalSend = proto.send as SendMethod;
    proto.send = this.wrap(this.originalSend);
  }

  protected removePatches(): void {
    if (this.proto && this.originalSend) {
      this.proto.send = this.originalSend;
    }
    this.proto = undefined;
    this.originalSend = undefined;
  }

  private wrap(original: SendMethod): SendMethod {
    const normalize = this.normalize.bind(this);
    const recordCaptured = this.recordCaptured.bind(this);
    const client = this.client;

    const submitResult = async (
      model: string,
      raw: Record<string, unknown>,
      latencyMs: number,
      status: UsageStatus,
    ): Promise<void> => {
      const usage = normalize(raw, { model, latencyMs, status });
      recordCaptured();
      await submit(usage, client);
    };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return async function (this: any, ...args: unknown[]) {
      const command = args[0] as { constructor?: { name?: string }; input?: { modelId?: string } };
      const commandName = command?.constructor?.name ?? "";
      if (!CONVERSE_COMMANDS.has(commandName)) {
        return original.apply(this, args);
      }

      const model = command?.input?.modelId ?? "unknown";
      const start = Date.now();
      let result: unknown;
      try {
        result = await original.apply(this, args);
      } catch (err) {
        await submitResult(model, {}, Date.now() - start, "error");
        throw err;
      }

      if (commandName === "ConverseStreamCommand") {
        return wrapConverseStream(result, model, start, submitResult);
      }
      const raw = extract(result);
      await submitResult(model, raw, Date.now() - start, "success");
      return result;
    };
  }
}

/** The Converse Stream API returns `{ stream: AsyncIterable<...>, ... }`
 * — the stream's final event carries `{ metadata: { usage: {...} } }`.
 * Wraps only the inner `stream` field so the rest of the response
 * envelope passes through untouched. */
function wrapConverseStream(
  response: unknown,
  model: string,
  start: number,
  submitResult: (
    model: string,
    raw: Record<string, unknown>,
    latencyMs: number,
    status: UsageStatus,
  ) => Promise<void>,
): unknown {
  const envelope = response as { stream?: AsyncIterable<unknown> };
  if (!envelope?.stream) return response;

  const innerStream = envelope.stream;

  async function* generator(): AsyncGenerator<unknown, void, undefined> {
    let raw: Record<string, unknown> = {};
    let error: Error | undefined;
    try {
      for await (const event of innerStream) {
        const metadata = (event as { metadata?: unknown })?.metadata;
        if (metadata) raw = extract(metadata);
        yield event;
      }
    } catch (err) {
      error = err instanceof Error ? err : new Error(String(err));
      throw err;
    } finally {
      await submitResult(model, raw, Date.now() - start, error ? "error" : "success");
    }
  }

  return { ...envelope, stream: generator() };
}
