/**
 * BackgroundWorker — ties every reliability component together, per the
 * ticket's pipeline:
 *
 *     Memory Queue -> Background Worker -> Persistent Queue -> Compression
 *     -> Retry Engine -> Circuit Breaker -> Connection Pool -> Usage API
 *
 * Node has no real background thread the way Python does — this runs as
 * a self-rescheduling async loop (`setTimeout` chain, not `setInterval`,
 * so passes never overlap) on the same event loop as everything else.
 * `Costorah.track()` still never blocks on network: it only ever calls
 * `MemoryQueue.put()`, which is synchronous work plus (only under the
 * `"block"` overflow policy) an awaited timer — never a network call.
 *
 * Batch upload, honestly documented: EP-16's `POST /v1/ingest/usage`
 * ingestion endpoint (the "Usage API" node in the ticket's diagram)
 * accepts exactly one usage record per request — there is no multi-event
 * batch endpoint, and adding one would mean modifying a previous
 * Engineering Package's API surface, which the ticket says not to do
 * unless absolutely necessary. "Batching" here means what it can
 * honestly mean without that: the worker groups up to `batchSize` due
 * events per pass and delivers them concurrently over the pooled
 * connection, instead of one blocking round trip at a time — real
 * throughput improvement, but still one HTTP request per event, not
 * fewer HTTP requests than events.
 */

import type { ResolvedConfig } from "../config.js";
import { CircuitBreaker } from "./circuitBreaker.js";
import { compressionRatio, maybeCompress } from "./compression.js";
import { ConnectionPool } from "./connectionPool.js";
import { MemoryQueue } from "./memoryQueue.js";
import { BackpressureController, TelemetryMetrics } from "./metrics.js";
import { PersistentQueue } from "./persistentQueue.js";
import { isRetryable, RetryScheduler } from "./retry.js";
import type { OverflowPolicy, QueuedEvent } from "./types.js";

const INGEST_PATH = "/v1/ingest/usage";

export interface BackgroundWorkerOptions {
  queueSize?: number;
  overflowPolicy?: OverflowPolicy;
  persistentQueuePath?: string | undefined;
  compressionEnabled?: boolean;
  retryEnabled?: boolean;
  pollIntervalMs?: number;
  maxConcurrentDeliveries?: number;
  connectionPool?: ConnectionPool;
}

export class BackgroundWorker {
  readonly memoryQueue: MemoryQueue;
  readonly persistentQueue: PersistentQueue;
  readonly circuitBreaker = new CircuitBreaker();
  readonly metrics = new TelemetryMetrics();
  readonly backpressure = new BackpressureController();
  readonly compressionEnabled: boolean;

  private readonly retryScheduler = new RetryScheduler();
  private readonly retryEnabled: boolean;
  private readonly pool: ConnectionPool;
  private readonly pollIntervalMs: number;
  private readonly batchSize: number;
  private readonly maxConcurrent: number;

  private running = false;
  private stopping = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private currentPass: Promise<void> = Promise.resolve();

  constructor(config: ResolvedConfig, options: BackgroundWorkerOptions = {}) {
    this.memoryQueue = new MemoryQueue({
      maxSize: options.queueSize ?? 10_000,
      overflowPolicy: options.overflowPolicy ?? "drop_oldest",
    });
    this.persistentQueue = new PersistentQueue(options.persistentQueuePath);
    this.compressionEnabled = options.compressionEnabled ?? true;
    this.retryEnabled = options.retryEnabled ?? true;
    this.pool = options.connectionPool ?? new ConnectionPool(config);
    this.pollIntervalMs = options.pollIntervalMs ?? 200;
    this.batchSize = config.batchSize;
    this.maxConcurrent = options.maxConcurrentDeliveries ?? 10;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.stopping = false;
    this.backpressure.setWorkerStatus("running");
    this.scheduleNextPass(0);
  }

  private scheduleNextPass(delayMs: number): void {
    if (this.stopping) return;
    this.timer = setTimeout(() => {
      this.currentPass = this.pass()
        .then((didWork) => {
          this.scheduleNextPass(didWork ? 0 : this.pollIntervalMs);
        })
        .catch(() => {
          this.scheduleNextPass(this.pollIntervalMs);
        });
    }, delayMs);
  }

  /** One iteration: drain memory queue into persistence, then attempt
   * delivery of anything due. Resolves true if any work was done. */
  private async pass(): Promise<boolean> {
    await this.persistentQueue.whenReady();
    let didWork = false;

    const batch = this.memoryQueue.getBatch(this.batchSize);
    if (batch.length > 0) {
      this.persistentQueue.enqueueMany(batch);
      didWork = true;
    }

    if (this.circuitBreaker.state === "open") {
      return didWork;
    }

    const due = this.persistentQueue.dequeueDue(this.batchSize);
    if (due.length === 0) {
      return didWork;
    }

    for (let i = 0; i < due.length; i += this.maxConcurrent) {
      const slice = due.slice(i, i + this.maxConcurrent);
      await Promise.all(slice.map((event) => this.deliverOne(event)));
    }
    return true;
  }

  private async deliverOne(event: QueuedEvent): Promise<void> {
    if (!this.circuitBreaker.allowRequest()) return;

    let body: Uint8Array = new TextEncoder().encode(JSON.stringify(event.payload));
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.compressionEnabled) {
      const originalLength = body.byteLength;
      const result = maybeCompress(body);
      if (result.compressed) {
        this.metrics.recordCompression(compressionRatio(originalLength, result.body.byteLength));
        headers["Content-Encoding"] = "gzip";
        body = result.body;
      }
    }

    const start = Date.now();
    let response: Response;
    try {
      response = await this.pool.post(INGEST_PATH, body, headers);
    } catch (err) {
      this.onFailure(event, undefined, err instanceof Error ? err.message : String(err), start);
      return;
    }

    const elapsedMs = Date.now() - start;
    if (response.status === 200) {
      this.circuitBreaker.recordSuccess();
      this.persistentQueue.ack(event.eventId);
      this.metrics.recordUpload(elapsedMs, 1, true);
      return;
    }

    const detail = await response.text().catch(() => "");
    this.onFailure(event, response.status, detail.slice(0, 200), start);
  }

  private onFailure(
    event: QueuedEvent,
    statusCode: number | undefined,
    detail: string,
    start: number,
  ): void {
    this.metrics.recordUpload(Date.now() - start, 1, false);

    if (!this.retryEnabled || !isRetryable(statusCode)) {
      this.persistentQueue.ack(event.eventId);
      return;
    }

    this.circuitBreaker.recordFailure();
    this.metrics.recordRetry();
    const attempts = event.attempts + 1;
    const delaySeconds = this.retryScheduler.nextDelaySeconds(attempts);
    this.persistentQueue.markRetry(event.eventId, attempts, Date.now() + delaySeconds * 1000);
    void detail; // available for structured logging call sites
  }

  submit(event: QueuedEvent): Promise<boolean> {
    return this.memoryQueue.put(event);
  }

  /** Resolves true once the memory + persistent queues are drained, or
   * `timeoutMs` elapses. */
  async flush(timeoutMs = 10_000): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (this.memoryQueue.isEmpty() && this.persistentQueue.count() === 0) {
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
    return this.memoryQueue.isEmpty() && this.persistentQueue.count() === 0;
  }

  async shutdown(timeoutMs = 10_000): Promise<void> {
    if (!this.running) return;
    await this.flush(timeoutMs);
    this.backpressure.setWorkerStatus("stopped");
    this.stopping = true;
    this.running = false;
    if (this.timer) clearTimeout(this.timer);
    await this.currentPass.catch(() => undefined);
    await this.persistentQueue.close();
  }
}
