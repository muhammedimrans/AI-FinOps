import { gunzipSync } from "node:zlib";

import { describe, expect, it } from "vitest";

import { compressionRatio, maybeCompress } from "../../src/reliability/compression.js";

describe("maybeCompress", () => {
  it("does not compress a tiny payload", () => {
    const body = new TextEncoder().encode('{"a":1}');
    const result = maybeCompress(body, 1024);
    expect(result.compressed).toBe(false);
    expect(result.body).toBe(body);
  });

  it("compresses a large payload", () => {
    const body = new TextEncoder().encode("x".repeat(2000));
    const result = maybeCompress(body, 1024);
    expect(result.compressed).toBe(true);
    expect(result.body).not.toBe(body);
    expect(new TextDecoder().decode(gunzipSync(result.body))).toBe("x".repeat(2000));
  });
});

describe("compressionRatio", () => {
  it("reflects the reduction", () => {
    const body = new TextEncoder().encode("a".repeat(5000));
    const { body: compressed } = maybeCompress(body, 100);
    const ratio = compressionRatio(body.byteLength, compressed.byteLength);
    expect(ratio).toBeGreaterThan(0);
    expect(ratio).toBeLessThan(1);
  });

  it("handles zero original bytes", () => {
    expect(compressionRatio(0, 0)).toBe(1.0);
  });
});
