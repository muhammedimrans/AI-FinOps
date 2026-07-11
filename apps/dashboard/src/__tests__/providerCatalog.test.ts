import { describe, it, expect } from "vitest";
import {
  hasKnownUsageApi,
  parseOpenRouterModelId,
  KNOWN_USAGE_API_PROVIDERS,
  providerPlatformInfo,
} from "../lib/providerCatalog";

// EP-26.0.1
describe("KNOWN_USAGE_API_PROVIDERS / hasKnownUsageApi", () => {
  it("includes openrouter alongside openai and anthropic", () => {
    expect(KNOWN_USAGE_API_PROVIDERS.has("openai")).toBe(true);
    expect(KNOWN_USAGE_API_PROVIDERS.has("anthropic")).toBe(true);
    expect(KNOWN_USAGE_API_PROVIDERS.has("openrouter")).toBe(true);
  });

  it("does not include providers with no bulk usage API", () => {
    expect(hasKnownUsageApi("google")).toBe(false);
    expect(hasKnownUsageApi("azure_openai")).toBe(false);
    expect(hasKnownUsageApi("grok")).toBe(false);
    expect(hasKnownUsageApi("ollama")).toBe(false);
  });

  it("hasKnownUsageApi reflects the set for openrouter", () => {
    expect(hasKnownUsageApi("openrouter")).toBe(true);
  });
});

describe("parseOpenRouterModelId", () => {
  it("parses a vendor/model slug with a known vendor label", () => {
    const parsed = parseOpenRouterModelId("anthropic/claude-sonnet-4");
    expect(parsed).not.toBeNull();
    expect(parsed?.vendorSlug).toBe("anthropic");
    expect(parsed?.vendorLabel).toBe("Anthropic");
    expect(parsed?.modelSlug).toBe("claude-sonnet-4");
  });

  it("falls back to the raw slug as the label for an unknown vendor", () => {
    const parsed = parseOpenRouterModelId("some-new-vendor/some-model");
    expect(parsed?.vendorLabel).toBe("some-new-vendor");
  });

  it("handles a model slug containing additional slashes", () => {
    const parsed = parseOpenRouterModelId("meta-llama/llama-3.1-405b/instruct");
    expect(parsed?.vendorSlug).toBe("meta-llama");
    expect(parsed?.vendorLabel).toBe("Meta");
    expect(parsed?.modelSlug).toBe("llama-3.1-405b/instruct");
  });

  it("returns null for a model id with no vendor prefix", () => {
    expect(parseOpenRouterModelId("gpt-4o")).toBeNull();
  });

  it("returns null for an empty or malformed id", () => {
    expect(parseOpenRouterModelId("")).toBeNull();
    expect(parseOpenRouterModelId("/no-vendor")).toBeNull();
    expect(parseOpenRouterModelId("no-model/")).toBeNull();
  });

  it("is case-insensitive when looking up the vendor label", () => {
    const parsed = parseOpenRouterModelId("OpenAI/gpt-4o");
    expect(parsed?.vendorLabel).toBe("OpenAI");
  });
});

// EP-26.0.2
describe("providerPlatformInfo", () => {
  it("returns AI Studio / Gemini API for google", () => {
    expect(providerPlatformInfo("google")).toEqual({
      platform: "AI Studio",
      service: "Gemini API",
    });
  });

  it("returns null for providers with no platform/service distinction", () => {
    expect(providerPlatformInfo("openai")).toBeNull();
    expect(providerPlatformInfo("anthropic")).toBeNull();
    expect(providerPlatformInfo("openrouter")).toBeNull();
    expect(providerPlatformInfo("azure_openai")).toBeNull();
    expect(providerPlatformInfo("grok")).toBeNull();
    expect(providerPlatformInfo("ollama")).toBeNull();
  });

  it("returns null for an unknown provider type", () => {
    expect(providerPlatformInfo("not-a-real-provider")).toBeNull();
  });
});
