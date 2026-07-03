import { describe, expect, it } from "vitest";

import { buildPayload } from "../src/client.js";
import { ValidationError } from "../src/errors.js";

describe("buildPayload", () => {
  it("builds the expected minimal payload", () => {
    const payload = buildPayload({ provider: "openai", model: "gpt-4.1", cost: 0.041 });
    expect(payload.provider).toBe("openai");
    expect(payload.model).toBe("gpt-4.1");
    expect(payload.cost).toBe(0.041);
    expect(payload.currency).toBe("USD");
    expect(payload.status).toBe("success");
    expect(payload.input_tokens).toBe(0);
    expect(payload.output_tokens).toBe(0);
    expect(payload).not.toHaveProperty("cached_tokens");
    expect(payload).not.toHaveProperty("total_tokens");
    expect(payload).not.toHaveProperty("latency_ms");
    expect(payload).not.toHaveProperty("region");
    expect(payload).not.toHaveProperty("project_id");
    expect(payload).not.toHaveProperty("timestamp");
    expect(payload.metadata).toEqual({});
    expect(String(payload.request_id)).toMatch(/^sdk_js_/);
  });

  it("includes optional fields when provided", () => {
    const timestamp = new Date("2026-01-01T00:00:00Z");
    const payload = buildPayload({
      provider: "anthropic",
      model: "claude-sonnet-4",
      inputTokens: 200,
      outputTokens: 80,
      cachedTokens: 10,
      totalTokens: 280,
      cost: 0.012,
      latencyMs: 410,
      region: "us-east-1",
      projectId: "proj_1",
      requestId: "my-custom-id",
      timestamp,
      metadata: { foo: "bar" },
    });

    expect(payload.cached_tokens).toBe(10);
    expect(payload.total_tokens).toBe(280);
    expect(payload.latency_ms).toBe(410);
    expect(payload.region).toBe("us-east-1");
    expect(payload.project_id).toBe("proj_1");
    expect(payload.request_id).toBe("my-custom-id");
    expect(payload.timestamp).toBe(timestamp.toISOString());
    expect(payload.metadata).toEqual({ foo: "bar" });
  });

  it("normalizes provider case and whitespace", () => {
    const payload = buildPayload({ provider: "  OpenAI  ", model: "gpt-4.1", cost: 0.01 });
    expect(payload.provider).toBe("openai");
  });

  it("rejects an unsupported provider", () => {
    expect(() =>
      buildPayload({ provider: "not-a-real-provider", model: "x", cost: 0 }),
    ).toThrow(ValidationError);
  });

  it("rejects a blank model", () => {
    expect(() => buildPayload({ provider: "openai", model: "   ", cost: 0 })).toThrow(
      /model must not be blank/,
    );
  });

  it.each(["inputTokens", "outputTokens"] as const)("rejects negative %s", (field) => {
    expect(() =>
      buildPayload({ provider: "openai", model: "gpt-4.1", cost: 0, [field]: -1 }),
    ).toThrow(ValidationError);
  });

  it("rejects negative cost", () => {
    expect(() => buildPayload({ provider: "openai", model: "gpt-4.1", cost: -1 })).toThrow(
      /cost must be/,
    );
  });

  it("rejects cachedTokens exceeding inputTokens", () => {
    expect(() =>
      buildPayload({
        provider: "openai",
        model: "gpt-4.1",
        cost: 0,
        inputTokens: 5,
        cachedTokens: 10,
      }),
    ).toThrow(/cachedTokens/);
  });

  it("rejects a totalTokens mismatch", () => {
    expect(() =>
      buildPayload({
        provider: "openai",
        model: "gpt-4.1",
        cost: 0,
        inputTokens: 5,
        outputTokens: 5,
        totalTokens: 100,
      }),
    ).toThrow(/totalTokens/);
  });
});
