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
 *
 * EP-18.3 reliability layer: `track()` validates its arguments
 * synchronously (cheap, no I/O) and then hands the built payload to a
 * background worker — it never makes a blocking network call itself, and
 * resolves in well under a millisecond. See `sdk/docs/RELIABILITY.md` for
 * the full pipeline (memory queue -> background worker -> persistent
 * queue -> compression -> retry -> circuit breaker -> connection pool)
 * and for what this means for `TrackResult` (it can no longer carry the
 * server-assigned `usageId`/`processedAt`/`duplicate` fields
 * synchronously — those are only known once the event is actually
 * delivered, which now happens off the critical path).
 * `client.flush()`/`client.shutdown()` await until pending events are
 * delivered when a caller needs that guarantee.
 */

import { tmpdir } from "node:os";

import { resolveConfig, type CostorahOptions, type ResolvedConfig } from "./config.js";
import { ValidationError } from "./errors.js";
import type { FetchLike } from "./http.js";
import type { Logger } from "./logging.js";
import {
  BackgroundWorker,
  ConnectionPool,
  HealthMonitor,
  makeQueuedEvent,
  type HealthSnapshot,
  type QueueStatsSnapshot,
} from "./reliability/index.js";
import { SUPPORTED_PROVIDERS, type TrackParams, type TrackResult } from "./types.js";
import { generateRequestId } from "./util.js";

export class Costorah {
  readonly config: ResolvedConfig;
  private readonly worker: BackgroundWorker;
  private readonly health_: HealthMonitor;

  constructor(options: CostorahOptions, _internal?: { fetchImpl?: FetchLike; logger?: Logger }) {
    this.config = resolveConfig(options);
    const pool = new ConnectionPool(this.config, _internal?.fetchImpl);
    this.worker = new BackgroundWorker(this.config, {
      queueSize: this.config.queueSize,
      overflowPolicy: this.config.overflowPolicy,
      persistentQueuePath: persistentQueuePath(this.config),
      compressionEnabled: this.config.compression,
      retryEnabled: this.config.retry,
      pollIntervalMs: Math.min(this.config.flushInterval * 1000, 500),
      connectionPool: pool,
    });
    this.health_ = new HealthMonitor(this.worker);
    this.worker.start();
  }

  /** Report one usage event. Validates its arguments synchronously
   * (rejecting immediately on bad input, same as before) and then hands
   * the payload to the background delivery pipeline — this method does
   * not make a network call and resolves immediately. See
   * `TrackResult`'s docstring and `sdk/docs/RELIABILITY.md` for what
   * "queued" means here. */
  async track(params: TrackParams): Promise<TrackResult> {
    const payload = buildPayload(params);
    const requestId = String(payload.request_id);
    const queued = await this.worker.submit(makeQueuedEvent(payload));
    return {
      success: queued,
      requestId,
      queued,
      usageId: undefined,
      processedAt: undefined,
      duplicate: false,
    };
  }

  /** Resolves true once every queued event has been delivered (or
   * permanently dropped), or `timeoutMs` elapses. Does not stop the
   * background worker — `track()` remains usable immediately afterward. */
  async flush(timeoutMs = 10_000): Promise<boolean> {
    return this.worker.flush(timeoutMs);
  }

  /** Graceful shutdown: flush pending events (best-effort, bounded by
   * `timeoutMs`), then stop the background worker. Safe to call more
   * than once. */
  async shutdown(timeoutMs = 10_000): Promise<void> {
    await this.worker.shutdown(timeoutMs);
  }

  /** Matches the ticket's literal shape: `{ worker: "running",
   * queue_depth: 24, retry_queue: 3, circuit: "closed", compression:
   * "enabled" }`. */
  health(): HealthSnapshot {
    return this.health_.snapshot();
  }

  /** Queue depth, dropped events, retry queue size, worker status, and
   * the TelemetryMetrics snapshot. */
  queueStats(): QueueStatsSnapshot {
    return this.health_.queueStats();
  }
}

function persistentQueuePath(config: ResolvedConfig): string | undefined {
  if (!config.persistentQueue) return undefined;
  // Namespaced by API key so the same key on the same machine reuses the
  // same file across restarts (needed for crash recovery to have
  // anything to recover) without colliding with a different key's queue.
  const hash = simpleHash(config.apiKey);
  return `${tmpdir()}/costorah/queue-${hash}.jsonl`;
}

function simpleHash(input: string): string {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    hash = (Math.imul(31, hash) + input.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(16);
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
