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

    expect(result.success).toBe(true);
    expect(result.usageId).toBe("u1");
    expect(captured).toHaveLength(1);
    expect(captured[0]!.url).toBe("https://api.costorah.com/v1/ingest/usage");
    expect(captured[0]!.auth).toBe("Bearer costorah_live_x");
  });

  it("surfaces the duplicate flag from a replayed request_id", async () => {
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
    const result = await client.track({ provider: "openai", model: "gpt-4.1", cost: 0.01 });
    expect(result.duplicate).toBe(true);
  });

  it("recovers a single track() call across a brief 503 outage", async () => {
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
      { apiKey: "costorah_live_x", maxRetries: 3 },
      { fetchImpl, logger: silentLogger() },
    );
    const result = await client.track({ provider: "openai", model: "gpt-4.1", cost: 0.01 });
    expect(result.success).toBe(true);
  });

  it("runs many concurrent track() calls safely (async concurrency safety)", async () => {
    const seenRequestIds = new Set<string>();
    const fetchImpl: FetchLike = async (_url, init) => {
      const body = JSON.parse(String(init?.body)) as { request_id: string };
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
    expect(seenRequestIds.size).toBe(100); // no cross-contamination between concurrent calls
    expect(results.every((r) => r.success)).toBe(true);
  });
});
