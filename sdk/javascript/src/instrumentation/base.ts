/**
 * BaseInstrumentor — the plugin interface every provider auto-instrumentor
 * implements, mirroring the Python SDK's `costorah.instrumentation.base`
 * (and, further back, the Monitoring Agent's `BaseCollector`, EP-17) so
 * the whole COSTORAH ecosystem shares one extensibility pattern across
 * languages: a handful of lifecycle methods, nothing provider-specific
 * anywhere else.
 *
 * Lifecycle
 * ---------
 *   constructor(options)   — cheap, no I/O, no patching yet
 *   instrument()            — apply monkey patches; idempotent
 *   uninstrument()           — restore original methods; idempotent
 *   isInstrumented()         — current patch state
 *   extractUsage(response)   — pull raw usage fields out of a
 *                              provider-native response object
 *   normalize(rawUsage, ..)  — build a costorah ExtractedUsage from
 *                              what extractUsage() returned
 */

import type { UsageStatus } from "../types.js";

export class InstrumentationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InstrumentationError";
  }
}

export interface ExtractedUsage {
  provider: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number | undefined;
  totalTokens: number | undefined;
  cost: number;
  currency: string;
  latencyMs: number | undefined;
  status: UsageStatus;
  requestId: string;
  timestamp: Date;
  metadata: Record<string, unknown>;
}

export function makeExtractedUsage(
  partial: Partial<ExtractedUsage> & Pick<ExtractedUsage, "provider" | "model" | "requestId">,
): ExtractedUsage {
  return {
    inputTokens: 0,
    outputTokens: 0,
    cachedTokens: undefined,
    totalTokens: undefined,
    cost: 0,
    currency: "USD",
    latencyMs: undefined,
    status: "success",
    timestamp: new Date(),
    metadata: {},
    ...partial,
  };
}

export interface InstrumentorOptions {
  enabled?: boolean;
  captureMetadata?: boolean;
  calculateCost?: boolean;
}

export abstract class BaseInstrumentor {
  abstract readonly name: string;

  readonly enabled: boolean;
  readonly captureMetadata: boolean;
  readonly calculateCostEnabled: boolean;

  private instrumented = false;
  private eventsCapturedTotal = 0;

  constructor(options: InstrumentorOptions = {}) {
    this.enabled = options.enabled ?? true;
    this.captureMetadata = options.captureMetadata ?? true;
    this.calculateCostEnabled = options.calculateCost ?? true;
  }

  /** Apply monkey patches. Idempotent — calling twice is a no-op. */
  instrument(): void {
    if (!this.enabled) return;
    if (this.instrumented) return;
    this.applyPatches();
    this.instrumented = true;
  }

  /** Restore original SDK methods exactly. Idempotent. */
  uninstrument(): void {
    if (!this.instrumented) return;
    this.removePatches();
    this.instrumented = false;
  }

  isInstrumented(): boolean {
    return this.instrumented;
  }

  protected markInstrumented(): void {
    this.instrumented = true;
  }

  protected markUninstrumented(): void {
    this.instrumented = false;
  }

  /** Subclasses: apply monkey patches here. Must throw
   * InstrumentationError (not a bare error) if the target SDK isn't
   * installed/compatible. */
  protected abstract applyPatches(): void;

  /** Subclasses: undo applyPatches() exactly. */
  protected abstract removePatches(): void;

  /** Pull raw usage fields out of a provider-native response object.
   * Pure, no I/O — independently testable against a fixture response. */
  abstract extractUsage(response: unknown): Record<string, unknown>;

  /** Convert extractUsage()'s output into a common ExtractedUsage. Pure
   * function, no I/O. */
  abstract normalize(
    rawUsage: Record<string, unknown>,
    context: { model: string; latencyMs: number; status: UsageStatus; requestId?: string },
  ): ExtractedUsage;

  protected recordCaptured(count = 1): void {
    this.eventsCapturedTotal += count;
  }

  get eventsCaptured(): number {
    return this.eventsCapturedTotal;
  }
}
