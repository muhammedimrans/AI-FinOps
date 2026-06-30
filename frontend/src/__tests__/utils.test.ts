import { describe, it, expect } from "vitest";
import {
  formatCost,
  formatNumber,
  formatTokens,
  modelDisplayName,
  providerDisplayName,
  trendIcon,
} from "../lib/utils";

// Regression tests for EP-11.5 utility functions

describe("formatCost", () => {
  it("formats USD currency", () => {
    expect(formatCost(1234.56, "USD")).toBe("$1,234.56");
  });

  it("returns em-dash for NaN input", () => {
    expect(formatCost("not-a-number", "USD")).toBe("—");
  });

  it("accepts numeric string input", () => {
    // Intl.NumberFormat trims trailing zeros, so 50.25 → $50.25
    expect(formatCost("50.25", "USD")).toBe("$50.25");
  });

  it("compact notation abbreviates large values", () => {
    const result = formatCost(1_500_000, "USD", true);
    expect(result).toMatch(/\$1\.5M/);
  });
});

describe("formatNumber", () => {
  it("returns em-dash for NaN", () => {
    expect(formatNumber(NaN)).toBe("—");
  });

  it("formats compact", () => {
    expect(formatNumber(1500, true)).toBe("1.5K");
  });

  it("formats standard", () => {
    expect(formatNumber(1500)).toBe("1,500");
  });
});

describe("formatTokens", () => {
  it("formats billions", () => {
    expect(formatTokens(2_000_000_000)).toBe("2.0B");
  });

  it("formats millions", () => {
    expect(formatTokens(1_500_000)).toBe("1.5M");
  });

  it("formats thousands", () => {
    expect(formatTokens(4_200)).toBe("4.2K");
  });

  it("formats small values as-is", () => {
    expect(formatTokens(500)).toBe("500");
  });
});

describe("trendIcon", () => {
  it("returns up for positive trend above threshold", () => {
    expect(trendIcon(1.0)).toBe("up");
  });

  it("returns down for negative trend below threshold", () => {
    expect(trendIcon(-1.0)).toBe("down");
  });

  it("returns flat for near-zero trend", () => {
    expect(trendIcon(0.05)).toBe("flat");
    expect(trendIcon(-0.05)).toBe("flat");
  });
});

describe("modelDisplayName", () => {
  it("maps known model IDs to display names", () => {
    expect(modelDisplayName("gpt-4o")).toBe("GPT-4o");
    expect(modelDisplayName("claude-3-5-sonnet")).toBe("Claude 3.5 Sonnet");
  });

  it("returns the raw ID for unknown models", () => {
    expect(modelDisplayName("some-unknown-model-v9")).toBe("some-unknown-model-v9");
  });
});

describe("providerDisplayName", () => {
  it("maps known providers", () => {
    expect(providerDisplayName("openai")).toBe("OpenAI");
    expect(providerDisplayName("anthropic")).toBe("Anthropic");
  });

  it("capitalizes unknown providers", () => {
    expect(providerDisplayName("cohere")).toBe("Cohere");
  });
});
