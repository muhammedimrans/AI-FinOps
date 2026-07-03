import { describe, expect, it } from "vitest";

import { CircuitBreaker } from "../../src/reliability/circuitBreaker.js";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe("CircuitBreaker", () => {
  it("starts closed", () => {
    const cb = new CircuitBreaker();
    expect(cb.state).toBe("closed");
    expect(cb.allowRequest()).toBe(true);
  });

  it("opens after the failure threshold", () => {
    const cb = new CircuitBreaker({ failureThreshold: 3 });
    cb.recordFailure();
    expect(cb.state).toBe("closed");
    cb.recordFailure();
    expect(cb.state).toBe("closed");
    cb.recordFailure();
    expect(cb.state).toBe("open");
    expect(cb.allowRequest()).toBe(false);
  });

  it("success resets the consecutive-failure count", () => {
    const cb = new CircuitBreaker({ failureThreshold: 3 });
    cb.recordFailure();
    cb.recordFailure();
    cb.recordSuccess();
    cb.recordFailure();
    cb.recordFailure();
    expect(cb.state).toBe("closed");
  });

  it("transitions to half_open after the recovery timeout", async () => {
    const cb = new CircuitBreaker({ failureThreshold: 1, recoveryTimeoutMs: 50 });
    cb.recordFailure();
    expect(cb.state).toBe("open");
    await sleep(60);
    expect(cb.state).toBe("half_open");
  });

  it("half_open probe success closes the circuit", async () => {
    const cb = new CircuitBreaker({ failureThreshold: 1, recoveryTimeoutMs: 50, halfOpenMaxCalls: 1 });
    cb.recordFailure();
    await sleep(60);
    expect(cb.allowRequest()).toBe(true);
    cb.recordSuccess();
    expect(cb.state).toBe("closed");
  });

  it("half_open probe failure reopens the circuit", async () => {
    const cb = new CircuitBreaker({ failureThreshold: 1, recoveryTimeoutMs: 50, halfOpenMaxCalls: 1 });
    cb.recordFailure();
    await sleep(60);
    expect(cb.allowRequest()).toBe(true);
    cb.recordFailure();
    expect(cb.state).toBe("open");
  });

  it("bounds concurrent half_open probes", async () => {
    const cb = new CircuitBreaker({ failureThreshold: 1, recoveryTimeoutMs: 50, halfOpenMaxCalls: 1 });
    cb.recordFailure();
    await sleep(60);
    expect(cb.allowRequest()).toBe(true);
    expect(cb.allowRequest()).toBe(false);
  });
});
