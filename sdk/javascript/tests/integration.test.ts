import { describe, expect, it, vi } from "vitest";

import { Costorah } from "../src/client.js";
import type { FetchLike } from "../src/http.js";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

function silentLogger() {
  return { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() };
}

describe("Costorah integration", () => {
  it("tracks a usage event end to end", async () => {
    const captured: { url: string; auth: string }[] = [];
    const fetchImpl: FetchLike = async (url, init) => {
      captured.push({
        url: String(url),
        auth: (init?.headers as Record<string, string>).Authorization ?? "",
      });
      return jsonResponse(200, {
        success: true,
        usage_id: "u1",
        request_id: "sdk_js_test",
        processed_at: "2026-01-01T00:00:00Z",
        duplicate: false,
      });
    };

    const client = new Costorah(
      { apiKey: "costorah_live_x" },
      { fetchImpl, logger: silentLogger() },
    );
    const result = await client.track({
      provider: "anthropic",
      model: "claude-sonnet-4",
      inputTokens: 200,
      outputTokens: 80,
      cost: 0.012,
      latencyMs: 410,
    });

    // track() no longer waits for delivery (EP-18.3) — verify actual
    // delivery via flush() + the mock fetch's captured requests, not via
    // TrackResult's fields (which no longer carry the server's response).
    expect(result.success).toBe(true);
    expect(result.queued).toBe(true);
    expect(await client.flush(5000)).toBe(true);
    expect(captured).toHaveLength(1);
    expect(captured[0]!.url).toBe("https://api.costorah.com/v1/ingest/usage");
    expect(captured[0]!.auth).toBe("Bearer costorah_live_x");
  });

  it("delivery outcome (e.g. a duplicate response) is observable via queueStats after flush", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(200, {
        success: true,
        usage_id: "u1",
        request_id: "r1",
        processed_at: "2026-01-01T00:00:00Z",
        duplicate: true,
      });
    const client = new Costorah(
      { apiKey: "costorah_live_x" },
      { fetchImpl, logger: silentLogger() },
    );
    await client.track({ provider: "openai", model: "gpt-4.1", cost: 0.01 });
    expect(await client.flush(5000)).toBe(true);
    expect(client.queueStats().sentTotal).toBe(1);
  });

  it("recovers a track() call across a brief 503 outage without losing it", async () => {
    let failuresLeft = 2;
    const fetchImpl: FetchLike = async () => {
      if (failuresLeft > 0) {
        failuresLeft -= 1;
        return jsonResponse(503, { detail: "down" });
      }
      return jsonResponse(200, {
        success: true,
        usage_id: "u1",
        request_id: "r1",
        processed_at: "2026-01-01T00:00:00Z",
        duplicate: false,
      });
    };
    const client = new Costorah(
      { apiKey: "costorah_live_x" },
      { fetchImpl, logger: silentLogger() },
    );
    const result = await client.track({ provider: "openai", model: "gpt-4.1", cost: 0.01 });
    expect(result.queued).toBe(true);
    // Two 1s/2s backoff delays before the third (successful) attempt.
    expect(await client.flush(10_000)).toBe(true);
    expect(client.queueStats().sentTotal).toBe(1);
    expect(failuresLeft).toBe(0);
  });

  it("runs many concurrent track() calls safely (async concurrency safety)", async () => {
    const seenRequestIds = new Set<string>();
    const fetchImpl: FetchLike = async (_url, init) => {
      // The reliability layer always sends the body as a Uint8Array (EP-18.3
      // — see reliability/connectionPool.ts), not a plain string.
      const raw = init?.body;
      const text =
        raw instanceof Uint8Array ? new TextDecoder().decode(raw) : String(raw ?? "{}");
      const body = JSON.parse(text) as { request_id: string };
      seenRequestIds.add(body.request_id);
      return jsonResponse(200, {
        success: true,
        usage_id: `u_${body.request_id}`,
        request_id: body.request_id,
        processed_at: "2026-01-01T00:00:00Z",
        duplicate: false,
      });
    };
    const client = new Costorah(
      { apiKey: "costorah_live_x" },
      { fetchImpl, logger: silentLogger() },
    );

    const results = await Promise.all(
      Array.from({ length: 100 }, (_, i) =>
        client.track({
          provider: "openai",
          model: "gpt-4.1",
          cost: 0.001,
          requestId: `concurrent-${i}`,
        }),
      ),
    );

    expect(results).toHaveLength(100);
    expect(results.every((r) => r.success)).toBe(true);
    expect(await client.flush(10_000)).toBe(true);
    expect(seenRequestIds.size).toBe(100); // no cross-contamination between concurrent calls
  });
});
