/**
 * SDK configuration. See `sdk/shared/API_CONTRACT.md` for the exact
 * meaning of each field — every COSTORAH SDK exposes the same keys with
 * the same defaults.
 */

import { ConfigurationError } from "./errors.js";

const DEFAULT_ENDPOINT = "https://api.costorah.com";

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

  return {
    apiKey,
    endpoint,
    timeout,
    batchSize,
    flushInterval,
    maxRetries,
    verifyTls: options.verifyTls ?? true,
  };
}
