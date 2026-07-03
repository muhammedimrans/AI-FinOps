import { describe, expect, it } from "vitest";

import { calculateCost, hasPricing } from "../../src/instrumentation/pricing.js";

describe("calculateCost", () => {
  it("computes cost for a known model", () => {
    const result = calculateCost("openai", "gpt-4o-mini", 1000, 500);
    expect(result.estimated).toBe(true);
    // 1000 * 0.00000015 + 500 * 0.0000006 = 0.00015 + 0.0003 = 0.00045
    expect(result.cost).toBeCloseTo(0.00045, 8);
  });

  it("returns cost 0 and estimated=false for an unknown model", () => {
    const result = calculateCost("openai", "totally-made-up-model", 1000, 500);
    expect(result.cost).toBe(0);
    expect(result.estimated).toBe(false);
  });

  it("returns cost 0 and estimated=false for an unknown provider", () => {
    const result = calculateCost("not-a-real-provider", "gpt-4o", 1000, 500);
    expect(result.cost).toBe(0);
    expect(result.estimated).toBe(false);
  });

  it("handles zero tokens", () => {
    const result = calculateCost("openai", "gpt-4o", 0, 0);
    expect(result.cost).toBe(0);
    expect(result.estimated).toBe(true);
  });

  it("rounds to 8 decimal places", () => {
    const result = calculateCost("openai", "gpt-4o-mini", 1, 1);
    expect(Number.isInteger(result.cost * 1e8)).toBe(true);
  });
});

describe("hasPricing", () => {
  it("is true for a known provider/model pair", () => {
    expect(hasPricing("anthropic", "claude-sonnet-4")).toBe(true);
  });

  it("is false for an unknown pair", () => {
    expect(hasPricing("anthropic", "claude-unreleased-model")).toBe(false);
  });
});
