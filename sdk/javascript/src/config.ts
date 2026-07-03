/**
 * SDK configuration. See `sdk/shared/API_CONTRACT.md` for the exact
 * meaning of each field — every COSTORAH SDK exposes the same keys with
 * the same defaults.
 */

import { ConfigurationError } from "./errors.js";

const DEFAULT_ENDPOINT = "https://api.costorah.com";

import type { OverflowPolicy } from "./reliability/types.js";

export interface CostorahOptions {
  apiKey: string;
  endpoint?: string;
  /** Per-request HTTP timeout, in seconds (matches every other COSTORAH
   * SDK's `timeout` unit — see sdk/shared/API_CONTRACT.md). Default: 30. */
  timeout?: number;
  batchSize?: number;
  /** Seconds. Default: 5. */
  flushInterval?: number;
  maxRetries?: number;
  verifyTls?: boolean;
  /** EP-18.3 reliability layer — see sdk/docs/RELIABILITY.md. */
  queueSize?: number;
  overflowPolicy?: OverflowPolicy;
  persistentQueue?: boolean;
  compression?: boolean;
  retry?: boolean;
}

export interface ResolvedConfig {
  apiKey: string;
  endpoint: string;
  /** Seconds. */
  timeout: number;
  batchSize: number;
  /** Seconds. */
  flushInterval: number;
  maxRetries: number;
  verifyTls: boolean;
  queueSize: number;
  overflowPolicy: OverflowPolicy;
  persistentQueue: boolean;
  compression: boolean;
  retry: boolean;
}

export function resolveConfig(options: CostorahOptions): ResolvedConfig {
  const apiKey = options.apiKey;
  if (!apiKey) {
    throw new ConfigurationError("apiKey is required");
  }
  if (!apiKey.startsWith("costorah_live_")) {
    throw new ConfigurationError("apiKey must start with 'costorah_live_'");
  }

  const endpointRaw = options.endpoint ?? DEFAULT_ENDPOINT;
  if (!endpointRaw.startsWith("http://") && !endpointRaw.startsWith("https://")) {
    throw new ConfigurationError("endpoint must start with http:// or https://");
  }
  const endpoint = endpointRaw.replace(/\/+$/, "");

  const timeout = options.timeout ?? 30;
  if (timeout <= 0) {
    throw new ConfigurationError("timeout must be positive");
  }

  const batchSize = options.batchSize ?? 25;
  if (batchSize <= 0) {
    throw new ConfigurationError("batchSize must be positive");
  }

  const flushInterval = options.flushInterval ?? 5;
  if (flushInterval <= 0) {
    throw new ConfigurationError("flushInterval must be positive");
  }

  const maxRetries = options.maxRetries ?? 3;
  if (maxRetries < 0) {
    throw new ConfigurationError("maxRetries must be >= 0");
  }

  const queueSize = options.queueSize ?? 10_000;
  if (queueSize <= 0) {
    throw new ConfigurationError("queueSize must be positive");
  }

  const overflowPolicy = options.overflowPolicy ?? "drop_oldest";
  if (!["drop_newest", "drop_oldest", "block"].includes(overflowPolicy)) {
    throw new ConfigurationError("overflowPolicy must be one of: drop_newest, drop_oldest, block");
  }

  return {
    apiKey,
    endpoint,
    timeout,
    batchSize,
    flushInterval,
    maxRetries,
    verifyTls: options.verifyTls ?? true,
    queueSize,
    overflowPolicy,
    persistentQueue: options.persistentQueue ?? false,
    compression: options.compression ?? true,
    retry: options.retry ?? true,
  };
}
