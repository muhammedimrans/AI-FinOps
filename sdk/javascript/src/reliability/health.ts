/**
 * HealthMonitor — formats the exact `client.health()` shape from the
 * ticket:
 *
 *     {
 *       "worker": "running",
 *       "queue_depth": 24,
 *       "retry_queue": 3,
 *       "circuit": "closed",
 *       "compression": "enabled"
 *     }
 */

import type { BackgroundWorker } from "./worker.js";

export interface HealthSnapshot {
  worker: string;
  queue_depth: number;
  retry_queue: number;
  circuit: string;
  compression: string;
}

export interface QueueStatsSnapshot {
  queueDepth: number;
  droppedEvents: number;
  retryQueueSize: number;
  workerStatus: string;
  sentTotal: number;
  failedTotal: number;
  retryCount: number;
  avgUploadLatencyMs: number;
  compressionRatio: number | null;
  lastBatchSize: number;
  workerUptimeSeconds: number;
}

export class HealthMonitor {
  constructor(private readonly worker: BackgroundWorker) {}

  snapshot(): HealthSnapshot {
    const w = this.worker;
    return {
      worker: w.backpressure.workerStatus,
      queue_depth: w.memoryQueue.size,
      retry_queue: w.persistentQueue.count(),
      circuit: w.circuitBreaker.state,
      compression: w.compressionEnabled ? "enabled" : "disabled",
    };
  }

  queueStats(): QueueStatsSnapshot {
    const w = this.worker;
    const metrics = w.metrics.snapshot();
    return {
      queueDepth: w.memoryQueue.size,
      droppedEvents: w.memoryQueue.dropped,
      retryQueueSize: w.persistentQueue.count(),
      workerStatus: w.backpressure.workerStatus,
      ...metrics,
    };
  }
}
