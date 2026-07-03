import { describe, expect, it } from "vitest";

import {
  DEFAULT_BACKOFF_SECONDS,
  isRetryable,
  RetryScheduler,
} from "../../src/reliability/retry.js";

describe("DEFAULT_BACKOFF_SECONDS", () => {
  it("matches the ticket's schedule", () => {
    expect(DEFAULT_BACKOFF_SECONDS).toEqual([1, 2, 4, 8, 16, 30, 60, 120, 300]);
  });
});

describe("RetryScheduler", () => {
  it("follows the schedule", () => {
    const scheduler = new RetryScheduler();
    expect(scheduler.nextDelaySeconds(1)).toBe(1);
    expect(scheduler.nextDelaySeconds(2)).toBe(2);
    expect(scheduler.nextDelaySeconds(3)).toBe(4);
    expect(scheduler.nextDelaySeconds(9)).toBe(300);
  });

  it("holds at the last value beyond schedule length", () => {
    const scheduler = new RetryScheduler();
    expect(scheduler.nextDelaySeconds(20)).toBe(300);
    expect(scheduler.nextDelaySeconds(1000)).toBe(300);
  });

  it("treats zero/negative attempt as the first attempt", () => {
    const scheduler = new RetryScheduler();
    expect(scheduler.nextDelaySeconds(0)).toBe(1);
    expect(scheduler.nextDelaySeconds(-5)).toBe(1);
  });

  it("rejects an empty schedule", () => {
    expect(() => new RetryScheduler([])).toThrow();
  });
});

describe("isRetryable", () => {
  it("never retries client errors", () => {
    for (const code of [400, 401, 403, 404]) {
      expect(isRetryable(code)).toBe(false);
    }
  });

  it("retries transient errors", () => {
    for (const code of [408, 429, 500, 502, 503, 504]) {
      expect(isRetryable(code)).toBe(true);
    }
  });

  it("retries a network error with no status code", () => {
    expect(isRetryable(undefined)).toBe(true);
  });

  it("defaults an unknown 5xx to retryable", () => {
    expect(isRetryable(599)).toBe(true);
  });

  it("defaults an unknown 4xx to not retryable", () => {
    expect(isRetryable(418)).toBe(false);
  });
});
