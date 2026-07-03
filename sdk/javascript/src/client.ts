/**
 * Costorah — the SDK's public entry point.
 *
 *     import { Costorah } from "@costorah/sdk";
 *
 *     const client = new Costorah({ apiKey: process.env.COSTORAH_API_KEY! });
 *     await client.track({
 *       provider: "anthropic",
 *       model: "claude-sonnet-4",
 *       inputTokens: 200,
 *       outputTokens: 80,
 *       cost: 0.012,
 *       latencyMs: 410,
 *     });
 *
 * Safe for concurrent async operations: a single `Costorah` instance can
 * be `await`ed from many places at once — each `track()` call is
 * independent and holds no shared mutable state beyond the HTTP fetch
 * implementation itself.
 */

import { resolveConfig, type CostorahOptions, type ResolvedConfig } from "./config.js";
import { ValidationError } from "./errors.js";
import { HttpTransport, type FetchLike } from "./http.js";
import type { Logger } from "./logging.js";
import { SUPPORTED_PROVIDERS, type TrackParams, type TrackResult } from "./types.js";
import { generateRequestId } from "./util.js";

export class Costorah {
  readonly config: ResolvedConfig;
  private readonly transport: HttpTransport;

  constructor(options: CostorahOptions, _internal?: { fetchImpl?: FetchLike; logger?: Logger }) {
    this.config = resolveConfig(options);
    this.transport = new HttpTransport(this.config, _internal?.fetchImpl, _internal?.logger);
  }

  /** Manually report one usage event. See `sdk/shared/API_CONTRACT.md`
   * for the exact field semantics — they match EP-16's ingestion API
   * one-to-one. Rejects with a costorah error on any failure; never
   * resolves with a partial/ambiguous result. */
  async track(params: TrackParams): Promise<TrackResult> {
    const payload = buildPayload(params);
    const body = await this.transport.postUsageEvent(payload);
    return {
      success: body.success ?? true,
      usageId: body.usage_id,
      requestId: body.request_id,
      processedAt: body.processed_at,
      duplicate: body.duplicate ?? false,
    };
  }
}

const SUPPORTED_PROVIDER_SET: ReadonlySet<string> = new Set(SUPPORTED_PROVIDERS);

export function buildPayload(params: TrackParams): Record<string, unknown> {
  const provider = params.provider.trim().toLowerCase();
  if (!SUPPORTED_PROVIDER_SET.has(provider)) {
    throw new ValidationError(
      `Unsupported provider "${params.provider}". Must be one of: ${SUPPORTED_PROVIDERS.join(", ")}`,
    );
  }
  if (!params.model || !params.model.trim()) {
    throw new ValidationError("model must not be blank");
  }
  const inputTokens = params.inputTokens ?? 0;
  const outputTokens = params.outputTokens ?? 0;
  if (inputTokens < 0 || outputTokens < 0) {
    throw new ValidationError("inputTokens and outputTokens must be >= 0");
  }
  if (params.cost < 0) {
    throw new ValidationError("cost must be >= 0");
  }
  if (params.cachedTokens !== undefined && params.cachedTokens > inputTokens) {
    throw new ValidationError("cachedTokens must not exceed inputTokens");
  }
  if (
    params.totalTokens !== undefined &&
    params.totalTokens !== inputTokens + outputTokens
  ) {
    throw new ValidationError(
      `totalTokens (${params.totalTokens}) must equal inputTokens + outputTokens (${
        inputTokens + outputTokens
      })`,
    );
  }

  const payload: Record<string, unknown> = {
    provider,
    model: params.model.trim(),
    request_id: params.requestId ?? generateRequestId(),
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    cost: params.cost,
    currency: params.currency ?? "USD",
    status: params.status ?? "success",
    metadata: params.metadata ?? {},
  };
  if (params.cachedTokens !== undefined) payload.cached_tokens = params.cachedTokens;
  if (params.totalTokens !== undefined) payload.total_tokens = params.totalTokens;
  if (params.latencyMs !== undefined) payload.latency_ms = params.latencyMs;
  if (params.region !== undefined) payload.region = params.region;
  if (params.projectId !== undefined) payload.project_id = params.projectId;
  if (params.timestamp !== undefined) payload.timestamp = params.timestamp.toISOString();
  return payload;
}
