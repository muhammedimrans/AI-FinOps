import { describe, expect, it, vi } from "vitest";

import { resolveConfig } from "../src/config.js";
import {
  AuthenticationError,
  NetworkError,
  RateLimitError,
  ServerError,
  ValidationError,
} from "../src/errors.js";
import { HttpTransport, type FetchLike } from "../src/http.js";

const successBody = {
  success: true,
  usage_id: "u1",
  request_id: "r1",
  processed_at: "2026-01-01T00:00:00Z",
  duplicate: false,
};

function jsonResponse(status: number, body: unknown, headers?: Record<string, string>): Response {
  return headers === undefined
    ? new Response(JSON.stringify(body), { status })
    : new Response(JSON.stringify(body), { status, headers });
}

function silentLogger() {
  return { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() };
}

describe("HttpTransport", () => {
  it("posts to /v1/ingest/usage with a Bearer auth header", async () => {
    let capturedUrl = "";
    let capturedAuth = "";
    const fetchImpl: FetchLike = async (url, init) => {
      capturedUrl = String(url);
      capturedAuth = (init?.headers as Record<string, string>).Authorization ?? "";
      return jsonResponse(200, successBody);
    };
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x" }),
      fetchImpl,
      silentLogger(),
    );
    const body = await transport.postUsageEvent({ provider: "openai" });
    expect(body.usage_id).toBe("u1");
    expect(capturedUrl).toBe("https://api.costorah.com/v1/ingest/usage");
    expect(capturedAuth).toBe("Bearer costorah_live_x");
  });

  it.each([401, 403])("raises AuthenticationError on %d without retrying", async (status) => {
    let calls = 0;
    const fetchImpl: FetchLike = async () => {
      calls += 1;
      return jsonResponse(status, { detail: "invalid key" });
    };
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x", maxRetries: 3 }),
      fetchImpl,
      silentLogger(),
    );
    await expect(transport.postUsageEvent({})).rejects.toThrow(AuthenticationError);
    expect(calls).toBe(1);
  });

  it.each([400, 404, 422])("raises ValidationError on %d without retrying", async (status) => {
    let calls = 0;
    const fetchImpl: FetchLike = async () => {
      calls += 1;
      return jsonResponse(status, { detail: "bad payload" });
    };
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x", maxRetries: 3 }),
      fetchImpl,
      silentLogger(),
    );
    await expect(transport.postUsageEvent({})).rejects.toThrow(ValidationError);
    expect(calls).toBe(1);
  });

  it("retries a 5xx then succeeds", async () => {
    const responses = [
      jsonResponse(503, { detail: "down" }),
      jsonResponse(200, successBody),
    ];
    const fetchImpl: FetchLike = async () => responses.shift()!;
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x", maxRetries: 3 }),
      fetchImpl,
      silentLogger(),
    );
    const start = Date.now();
    const body = await transport.postUsageEvent({});
    const elapsed = Date.now() - start;
    expect(body.usage_id).toBe("u1");
    expect(elapsed).toBeGreaterThanOrEqual(900); // ~1s first backoff, generous tolerance
  });

  it("exhausts retries on persistent 5xx and raises ServerError", async () => {
    let calls = 0;
    const fetchImpl: FetchLike = async () => {
      calls += 1;
      return jsonResponse(500, { detail: "boom" });
    };
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x", maxRetries: 2 }),
      fetchImpl,
      silentLogger(),
    );
    await expect(transport.postUsageEvent({})).rejects.toThrow(ServerError);
    expect(calls).toBe(3); // initial + 2 retries
  });

  it("honors Retry-After on 429", async () => {
    const responses = [
      jsonResponse(429, { detail: "slow down" }, { "Retry-After": "0.2" }),
      jsonResponse(200, successBody),
    ];
    const fetchImpl: FetchLike = async () => responses.shift()!;
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x", maxRetries: 3 }),
      fetchImpl,
      silentLogger(),
    );
    const start = Date.now();
    await transport.postUsageEvent({});
    const elapsed = Date.now() - start;
    expect(elapsed).toBeGreaterThanOrEqual(150);
    expect(elapsed).toBeLessThan(1000); // honored 0.2s, not the 1s default backoff
  });

  it("exhausts retries on persistent 429 and raises RateLimitError", async () => {
    const fetchImpl: FetchLike = async () =>
      jsonResponse(429, { detail: "slow down" }, { "Retry-After": "0.01" });
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x", maxRetries: 1 }),
      fetchImpl,
      silentLogger(),
    );
    await expect(transport.postUsageEvent({})).rejects.toThrow(RateLimitError);
  });

  it("treats a rejected fetch as a retryable NetworkError", async () => {
    let calls = 0;
    const fetchImpl: FetchLike = async () => {
      calls += 1;
      throw new Error("connection refused");
    };
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x", maxRetries: 1 }),
      fetchImpl,
      silentLogger(),
    );
    await expect(transport.postUsageEvent({})).rejects.toThrow(NetworkError);
    expect(calls).toBe(2);
  });

  it("truncates error detail and never echoes the full body", async () => {
    const fetchImpl: FetchLike = async () => jsonResponse(400, { detail: "x".repeat(2000) });
    const transport = new HttpTransport(
      resolveConfig({ apiKey: "costorah_live_x" }),
      fetchImpl,
      silentLogger(),
    );
    try {
      await transport.postUsageEvent({});
      expect.unreachable();
    } catch (err) {
      expect((err as Error).message.length).toBe(500);
    }
  });
});
