import { describe, expect, it } from "vitest";

import { resolveConfig } from "../src/config.js";
import { ConfigurationError } from "../src/errors.js";

describe("resolveConfig", () => {
  it("applies defaults", () => {
    const config = resolveConfig({ apiKey: "costorah_live_x" });
    expect(config.endpoint).toBe("https://api.costorah.com");
    expect(config.timeout).toBe(30);
    expect(config.batchSize).toBe(25);
    expect(config.flushInterval).toBe(5);
    expect(config.maxRetries).toBe(3);
    expect(config.verifyTls).toBe(true);
  });

  it("rejects a missing apiKey", () => {
    expect(() => resolveConfig({ apiKey: "" })).toThrow(ConfigurationError);
  });

  it("rejects an apiKey without the costorah_live_ prefix", () => {
    expect(() => resolveConfig({ apiKey: "sk-not-costorah" })).toThrow(/costorah_live_/);
  });

  it("rejects an endpoint without a scheme", () => {
    expect(() =>
      resolveConfig({ apiKey: "costorah_live_x", endpoint: "api.costorah.com" }),
    ).toThrow(/http/);
  });

  it("strips a trailing slash from the endpoint", () => {
    const config = resolveConfig({
      apiKey: "costorah_live_x",
      endpoint: "https://api.costorah.com/",
    });
    expect(config.endpoint).toBe("https://api.costorah.com");
  });

  it.each([
    ["timeout", 0],
    ["batchSize", 0],
    ["flushInterval", 0],
    ["maxRetries", -1],
  ])("rejects non-positive %s", (field, value) => {
    expect(() =>
      resolveConfig({ apiKey: "costorah_live_x", [field]: value }),
    ).toThrow(ConfigurationError);
  });
});
