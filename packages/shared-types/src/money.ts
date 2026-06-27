import type { Currency } from "./enums.js";

/**
 * Monetary amount.
 * amount is in the smallest unit of the currency (e.g. cents for USD).
 * All internal cost calculations use integer arithmetic to avoid float drift.
 */
export interface Money {
  readonly amount: number;
  readonly currency: Currency;
}

/** Cost breakdown per token type (all values in micro-USD, i.e. 1e-6 USD). */
export interface TokenCost {
  readonly inputCostMicroUsd: number;
  readonly outputCostMicroUsd: number;
  readonly cachedInputCostMicroUsd: number;
  readonly totalCostMicroUsd: number;
}

/** Token usage counts for a single inference call. */
export interface TokenUsage {
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly cachedInputTokens: number;
  readonly totalTokens: number;
}
