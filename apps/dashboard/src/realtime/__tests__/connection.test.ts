import { describe, expect, it } from "vitest";
import {
  buildWebSocketUrl,
  isRetryableCloseCode,
  reconnectDelayMs,
  WS_CLOSE_AUTH_FAILED,
  WS_CLOSE_HEARTBEAT_TIMEOUT,
  WS_CLOSE_RATE_LIMITED,
} from "../connection";

describe("buildWebSocketUrl", () => {
  it("converts http(s) to ws(s) and includes token + organization_id as query params", () => {
    const url = buildWebSocketUrl({
      baseUrl: "https://api.example.com",
      token: "abc123",
      organizationId: "org-1",
    });
    const parsed = new URL(url);
    expect(parsed.protocol).toBe("wss:");
    expect(parsed.pathname).toBe("/v1/ws");
    expect(parsed.searchParams.get("token")).toBe("abc123");
    expect(parsed.searchParams.get("organization_id")).toBe("org-1");
  });

  it("converts plain http to ws (not wss)", () => {
    const url = buildWebSocketUrl({
      baseUrl: "http://localhost:8000",
      token: "t",
      organizationId: "o",
    });
    expect(new URL(url).protocol).toBe("ws:");
  });
});

describe("reconnectDelayMs", () => {
  it("grows exponentially with attempt number", () => {
    const noJitter = () => 0.5; // random()=0.5 → jitter term is exactly 0
    const d0 = reconnectDelayMs(0, noJitter);
    const d1 = reconnectDelayMs(1, noJitter);
    const d2 = reconnectDelayMs(2, noJitter);
    expect(d1).toBeGreaterThan(d0);
    expect(d2).toBeGreaterThan(d1);
  });

  it("caps at the maximum delay for large attempt counts", () => {
    const noJitter = () => 0.5;
    const delay = reconnectDelayMs(20, noJitter);
    expect(delay).toBeLessThanOrEqual(30_000 * 1.0); // no positive jitter beyond cap logic
  });

  it("never returns a negative delay even with maximally negative jitter", () => {
    const alwaysZero = () => 0; // jitter term becomes -exponential*0.2
    const delay = reconnectDelayMs(0, alwaysZero);
    expect(delay).toBeGreaterThanOrEqual(0);
  });

  it("applies jitter so repeated calls at the same attempt aren't identical", () => {
    let call = 0;
    const values = [0.1, 0.9];
    const sequenced = () => values[call++ % values.length]!;
    const a = reconnectDelayMs(3, sequenced);
    const b = reconnectDelayMs(3, sequenced);
    expect(a).not.toBe(b);
  });
});

describe("isRetryableCloseCode", () => {
  it("treats auth failure as non-retryable", () => {
    expect(isRetryableCloseCode(WS_CLOSE_AUTH_FAILED)).toBe(false);
  });

  it("treats rate limiting and heartbeat timeout as retryable", () => {
    expect(isRetryableCloseCode(WS_CLOSE_RATE_LIMITED)).toBe(true);
    expect(isRetryableCloseCode(WS_CLOSE_HEARTBEAT_TIMEOUT)).toBe(true);
  });

  it("treats a normal close as retryable at this layer (caller decides whether to reconnect)", () => {
    expect(isRetryableCloseCode(1000)).toBe(true);
  });
});
