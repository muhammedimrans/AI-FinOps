/**
 * TelemetryMetrics and BackpressureController — the counters/gauges the
 * ticket's SDK Health API and Telemetry Metrics sections require.
 */

export interface MetricsSnapshot {
  sentTotal: number;
  failedTotal: number;
  retryCount: number;
  avgUploadLatencyMs: number;
  compressionRatio: number | null;
  lastBatchSize: number;
  workerUptimeSeconds: number;
}

export class TelemetryMetrics {
  private retryCountValue = 0;
  private uploadLatenciesMs: number[] = [];
  private lastCompressionRatio: number | null = null;
  private lastBatchSizeValue = 0;
  private sentTotalValue = 0;
  private failedTotalValue = 0;
  private readonly startedAt = Date.now();

  recordRetry(): void {
    this.retryCountValue += 1;
  }

  recordUpload(latencyMs: number, batchSize: number, success: boolean): void {
    this.uploadLatenciesMs.push(latencyMs);
    if (this.uploadLatenciesMs.length > 1000) {
      this.uploadLatenciesMs = this.uploadLatenciesMs.slice(-1000);
    }
    this.lastBatchSizeValue = batchSize;
    if (success) this.sentTotalValue += batchSize;
    else this.failedTotalValue += batchSize;
  }

  recordCompression(ratio: number): void {
    this.lastCompressionRatio = ratio;
  }

  get workerUptimeSeconds(): number {
    return (Date.now() - this.startedAt) / 1000;
  }

  snapshot(): MetricsSnapshot {
    const avgLatency =
      this.uploadLatenciesMs.length > 0
        ? this.uploadLatenciesMs.reduce((a, b) => a + b, 0) / this.uploadLatenciesMs.length
        : 0;
    return {
      sentTotal: this.sentTotalValue,
      failedTotal: this.failedTotalValue,
      retryCount: this.retryCountValue,
      avgUploadLatencyMs: Math.round(avgLatency * 100) / 100,
      compressionRatio: this.lastCompressionRatio,
      lastBatchSize: this.lastBatchSizeValue,
      workerUptimeSeconds: Math.round(this.workerUptimeSeconds * 10) / 10,
    };
  }
}

export type WorkerStatus = "running" | "stopped";

export class BackpressureController {
  private status: WorkerStatus = "stopped";

  setWorkerStatus(status: WorkerStatus): void {
    this.status = status;
  }

  get workerStatus(): WorkerStatus {
    return this.status;
  }
}
