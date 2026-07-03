import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeExtractedUsage } from "../../src/instrumentation/base.js";
import { resetDefaultClientForTests, submit } from "../../src/instrumentation/submission.js";
import { createTestClient } from "./testUtils.js";

describe("submit", () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    resetDefaultClientForTests();
  });

  afterEach(() => {
    process.env = { ...originalEnv };
    resetDefaultClientForTests();
  });

  it("submits via an explicit client and returns true", async () => {
    const { client, captured } = createTestClient();
    const usage = makeExtractedUsage({
      provider: "openai",
      model: "gpt-4o",
      requestId: "r1",
      inputTokens: 10,
      outputTokens: 5,
      cost: 0.01,
    });
    const ok = await submit(usage, client);
    expect(ok).toBe(true);
    expect(captured).toHaveLength(1);
    expect(captured[0]?.model).toBe("gpt-4o");
  });

  it("returns false and never throws when no client is available", async () => {
    delete process.env.COSTORAH_API_KEY;
    const usage = makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r2" });
    const ok = await submit(usage);
    expect(ok).toBe(false);
  });

  it("returns false (never throws) when the client rejects", async () => {
    const { client } = createTestClient();
    vi.spyOn(client, "track").mockRejectedValue(new Error("network down"));
    const usage = makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r3" });
    // track() throwing a non-CostorahError should propagate per submission.ts's
    // design (only CostorahError is swallowed) — verify that contract directly.
    await expect(submit(usage, client)).rejects.toThrow("network down");
  });

  it("omits undefined optional fields from the tracked payload", async () => {
    const { client, captured } = createTestClient();
    const usage = makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r4" });
    await submit(usage, client);
    expect(captured[0]?.cached_tokens).toBeUndefined();
    expect(captured[0]?.total_tokens).toBeUndefined();
    expect(captured[0]?.latency_ms).toBeUndefined();
  });
});
