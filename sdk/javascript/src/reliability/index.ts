/**
 * COSTORAH SDK reliability layer (EP-18.3): background delivery,
 * queueing, retry, circuit breaking, and compression so `track()` never
 * blocks the application on network I/O. See `sdk/docs/RELIABILITY.md`.
 */

export { BackgroundWorker } from "./worker.js";
export type { BackgroundWorkerOptions } from "./worker.js";
export { BackpressureController, TelemetryMetrics } from "./metrics.js";
export type { MetricsSnapshot, WorkerStatus } from "./metrics.js";
export { CircuitBreaker } from "./circuitBreaker.js";
export type { CircuitBreakerOptions, CircuitState } from "./circuitBreaker.js";
export { compressionRatio, maybeCompress } from "./compression.js";
export { ConnectionPool } from "./connectionPool.js";
export { HealthMonitor } from "./health.js";
export type { HealthSnapshot, QueueStatsSnapshot } from "./health.js";
export { MemoryQueue } from "./memoryQueue.js";
export type { MemoryQueueOptions } from "./memoryQueue.js";
export { PersistentQueue } from "./persistentQueue.js";
export { DEFAULT_BACKOFF_SECONDS, isRetryable, RetryScheduler } from "./retry.js";
export { makeQueuedEvent, OVERFLOW_POLICIES } from "./types.js";
export type { OverflowPolicy, QueuedEvent } from "./types.js";
