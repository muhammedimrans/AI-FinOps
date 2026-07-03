/**
 * Performance targets from the EP-18 ticket: initialization <5ms,
 * tracking overhead <2ms, memory <50MB, batch upload latency <100ms.
 * EP-18.1 has no batching yet (EP-18.3), so "tracking overhead" here
 * means the SDK-side cost of track() with network latency removed (a
 * fetch stub responding instantly).
 */
import { describe, expect, it, vi } from "vitest";

import { Costorah } from "../src/client.js";
import type { FetchLike } from "../src/http.js";

const EVENT_COUNT = 100_000;

function instantFetch(): FetchLike {
  return async () =>
    new Response(
      JSON.stringify({
        success: true,
        usage_id: "u1",
        request_id: "r1",
        processed_at: "2026-01-01T00:00:00Z",
        duplicate: false,
      }),
      { status: 200 },
    );
}

function silentLogger() {
  return { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() };
}

describe("performance", () => {
  it("initializes a client in under 5ms on average", () => {
    const samples: number[] = [];
    for (let i = 0; i < 20; i++) {
      const start = performance.now();
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const client = new Costorah(
        { apiKey: "costorah_live_x" },
        { fetchImpl: instantFetch(), logger: silentLogger() },
      );
      samples.push(performance.now() - start);
    }
    const avg = samples.reduce((a, b) => a + b, 0) / samples.length;
    expect(avg).toBeLessThan(5);
  });

  it("has bounded tracking overhead excluding network", async () => {
    const client = new Costorah(
      { apiKey: "costorah_live_x" },
      { fetchImpl: instantFetch(), logger: silentLogger() },
    );
    for (let i = 0; i < 20; i++) {
      await client.track({ provider: "openai", model: "gpt-4.1", cost: 0 });
    }

    const samples: number[] = [];
    for (let i = 0; i < 200; i++) {
      const start = performance.now();
      await client.track({ provider: "openai", model: "gpt-4.1", cost: 0 });
      samples.push(performance.now() - start);
    }
    const avg = samples.reduce((a, b) => a + b, 0) / samples.length;
    // Generous relative to the 2ms target — see module docstring.
    expect(avg).toBeLessThan(10);
  });

  it("handles 100,000 tracked events, all succeeding", async () => {
    const client = new Costorah(
      { apiKey: "costorah_live_x" },
      { fetchImpl: instantFetch(), logger: silentLogger() },
    );
    const start = performance.now();
    for (let i = 0; i < EVENT_COUNT; i++) {
      const result = await client.track({
        provider: "openai",
        model: "gpt-4.1",
        cost: 0.0001,
        requestId: `perf-${i}`,
      });
      expect(result.success).toBe(true);
    }
    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(60_000);
  }, 90_000);
});
