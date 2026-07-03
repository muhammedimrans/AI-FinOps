import { describe, expect, it } from "vitest";

import { Costorah } from "../../src/client.js";
import type { FetchLike } from "../../src/http.js";

/** The reliability layer always sends the body as a Uint8Array (EP-18.3
 * — see reliability/connectionPool.ts), not a plain string. */
function decodeBody(raw: unknown): string {
  if (raw instanceof Uint8Array) return new TextDecoder().decode(raw);
  return String(raw ?? "{}");
}

function instantFetch(): FetchLike {
  return async (_url, init) => {
    const body = JSON.parse(decodeBody(init?.body)) as { request_id?: string };
    return new Response(
      JSON.stringify({
        success: true,
        usage_id: "u1",
        request_id: body.request_id ?? "r1",
        processed_at: "2026-01-01T00:00:00Z",
        duplicate: false,
      }),
      { status: 200 },
    );
  };
}

describe("Costorah.health()", () => {
  it("matches the ticket shape", async () => {
    const client = new Costorah({ apiKey: "costorah_live_x" }, { fetchImpl: instantFetch() });
    const health = client.health();
    expect(Object.keys(health).sort()).toEqual(
      ["circuit", "compression", "queue_depth", "retry_queue", "worker"].sort(),
    );
    expect(health.worker).toBe("running");
    expect(health.circuit).toBe("closed");
    expect(health.compression).toBe("enabled");
    await client.shutdown();
    expect(client.health().worker).toBe("stopped");
  });

  it("reflects compression: false", () => {
    const client = new Costorah(
      { apiKey: "costorah_live_x", compression: false },
      { fetchImpl: instantFetch() },
    );
    expect(client.health().compression).toBe("disabled");
  });
});

describe("Costorah.queueStats()", () => {
  it("reflects activity", async () => {
    const client = new Costorah({ apiKey: "costorah_live_x" }, { fetchImpl: instantFetch() });
    for (let i = 0; i < 5; i++) {
      await client.track({ provider: "openai", model: "m", cost: 0, requestId: `r${i}` });
    }
    expect(await client.flush(5000)).toBe(true);
    const stats = client.queueStats();
    expect(stats.sentTotal).toBe(5);
    expect(stats.queueDepth).toBe(0);
    expect(stats.workerStatus).toBe("running");
    await client.shutdown();
  });
});

describe("Costorah.track() performance", () => {
  it("resolves in well under 1ms on average", async () => {
    const client = new Costorah({ apiKey: "costorah_live_x" }, { fetchImpl: instantFetch() });
    for (let i = 0; i < 20; i++) {
      await client.track({ provider: "openai", model: "m", cost: 0 });
    }

    const samples: number[] = [];
    for (let i = 0; i < 200; i++) {
      const start = performance.now();
      await client.track({ provider: "openai", model: "m", cost: 0 });
      samples.push(performance.now() - start);
    }
    const avg = samples.reduce((a, b) => a + b, 0) / samples.length;
    await client.shutdown();
    expect(avg).toBeLessThan(1.0);
  });

  it(
    "handles 100,000 queued events without blocking",
    async () => {
      const client = new Costorah(
        { apiKey: "costorah_live_x", queueSize: 200_000 },
        { fetchImpl: instantFetch() },
      );
      const start = performance.now();
      for (let i = 0; i < 100_000; i++) {
        const result = await client.track({
          provider: "openai",
          model: "m",
          cost: 0.0001,
          requestId: `perf-${i}`,
        });
        expect(result.success).toBe(true);
      }
      const elapsed = performance.now() - start;
      expect(elapsed).toBeLessThan(10_000);
      await client.shutdown();
    },
    90_000,
  );
});
