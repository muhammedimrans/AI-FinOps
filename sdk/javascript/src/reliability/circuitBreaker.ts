/**
 * CircuitBreaker — stops sending after repeated failures, probes
 * periodically, recovers automatically. Standard three-state design
 * (Closed/Open/Half-Open).
 */

export type CircuitState = "closed" | "open" | "half_open";

export interface CircuitBreakerOptions {
  failureThreshold?: number;
  recoveryTimeoutMs?: number;
  halfOpenMaxCalls?: number;
}

export class CircuitBreaker {
  private readonly failureThreshold: number;
  private readonly recoveryTimeoutMs: number;
  private readonly halfOpenMaxCalls: number;

  private stateValue: CircuitState = "closed";
  private consecutiveFailures = 0;
  private openedAt: number | undefined;
  private halfOpenCallsInFlight = 0;
  private halfOpenSuccesses = 0;

  constructor(options: CircuitBreakerOptions = {}) {
    this.failureThreshold = options.failureThreshold ?? 5;
    this.recoveryTimeoutMs = options.recoveryTimeoutMs ?? 30_000;
    this.halfOpenMaxCalls = options.halfOpenMaxCalls ?? 1;
    if (this.failureThreshold <= 0) throw new Error("failureThreshold must be positive");
    if (this.halfOpenMaxCalls <= 0) throw new Error("halfOpenMaxCalls must be positive");
  }

  get state(): CircuitState {
    this.maybeTransitionToHalfOpen();
    return this.stateValue;
  }

  private maybeTransitionToHalfOpen(): void {
    if (
      this.stateValue === "open" &&
      this.openedAt !== undefined &&
      Date.now() - this.openedAt >= this.recoveryTimeoutMs
    ) {
      this.stateValue = "half_open";
      this.halfOpenCallsInFlight = 0;
      this.halfOpenSuccesses = 0;
    }
  }

  /** Call before attempting delivery. False means: don't send, keep the
   * event queued for a later pass. */
  allowRequest(): boolean {
    const state = this.state;
    if (state === "closed") return true;
    if (state === "open") return false;
    if (this.halfOpenCallsInFlight < this.halfOpenMaxCalls) {
      this.halfOpenCallsInFlight += 1;
      return true;
    }
    return false;
  }

  recordSuccess(): void {
    if (this.stateValue === "half_open") {
      this.halfOpenSuccesses += 1;
      if (this.halfOpenSuccesses >= this.halfOpenMaxCalls) {
        this.stateValue = "closed";
        this.consecutiveFailures = 0;
        this.openedAt = undefined;
      }
    } else {
      this.consecutiveFailures = 0;
    }
  }

  recordFailure(): void {
    if (this.stateValue === "half_open") {
      this.stateValue = "open";
      this.openedAt = Date.now();
      this.halfOpenCallsInFlight = 0;
      this.halfOpenSuccesses = 0;
      return;
    }
    this.consecutiveFailures += 1;
    if (this.consecutiveFailures >= this.failureThreshold) {
      this.stateValue = "open";
      this.openedAt = Date.now();
    }
  }
}
