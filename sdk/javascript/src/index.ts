/**
 * @costorah/sdk — official JavaScript/TypeScript SDK for AI usage/cost
 * telemetry.
 *
 *     import { Costorah } from "@costorah/sdk";
 *
 *     const client = new Costorah({ apiKey: process.env.COSTORAH_API_KEY! });
 *     await client.track({ provider: "openai", model: "gpt-4.1", cost: 0.041 });
 */

export { Costorah } from "./client.js";
export type { CostorahOptions, ResolvedConfig } from "./config.js";
export {
  AuthenticationError,
  ConfigurationError,
  CostorahError,
  NetworkError,
  RateLimitError,
  ServerError,
  ValidationError,
} from "./errors.js";
export { createConsoleLogger } from "./logging.js";
export type { Logger, LogLevel } from "./logging.js";
export { SUPPORTED_PROVIDERS } from "./types.js";
export type { Provider, TrackParams, TrackResult, UsageStatus } from "./types.js";
export { VERSION } from "./version.js";

export { BaseInstrumentor, InstrumentationError } from "./instrumentation/base.js";
export type { ExtractedUsage, InstrumentorOptions } from "./instrumentation/base.js";
export { AnthropicInstrumentor } from "./instrumentation/anthropic.js";
export { AzureOpenAIInstrumentor } from "./instrumentation/azureOpenai.js";
export { BedrockInstrumentor } from "./instrumentation/bedrock.js";
export { CohereInstrumentor } from "./instrumentation/cohere.js";
export { GeminiInstrumentor } from "./instrumentation/google.js";
export { GrokInstrumentor } from "./instrumentation/grok.js";
export { MistralInstrumentor } from "./instrumentation/mistral.js";
export { OllamaInstrumentor } from "./instrumentation/ollama.js";
export { OpenAIInstrumentor } from "./instrumentation/openai.js";
export { OpenAICompatibleInstrumentor } from "./instrumentation/openaiCompatible.js";
export { OpenRouterInstrumentor } from "./instrumentation/openrouter.js";

export { BackgroundWorker } from "./reliability/worker.js";
export type { BackgroundWorkerOptions } from "./reliability/worker.js";
export { BackpressureController, TelemetryMetrics } from "./reliability/metrics.js";
export type { MetricsSnapshot, WorkerStatus } from "./reliability/metrics.js";
export { CircuitBreaker } from "./reliability/circuitBreaker.js";
export type { CircuitBreakerOptions, CircuitState } from "./reliability/circuitBreaker.js";
export { ConnectionPool } from "./reliability/connectionPool.js";
export { HealthMonitor } from "./reliability/health.js";
export type { HealthSnapshot, QueueStatsSnapshot } from "./reliability/health.js";
export { MemoryQueue } from "./reliability/memoryQueue.js";
export type { MemoryQueueOptions } from "./reliability/memoryQueue.js";
export { PersistentQueue } from "./reliability/persistentQueue.js";
export {
  DEFAULT_BACKOFF_SECONDS,
  isRetryable,
  RetryScheduler,
} from "./reliability/retry.js";
export type { OverflowPolicy } from "./reliability/types.js";
