import { describe, expect, it } from "vitest";

import { redact } from "../src/logging.js";

describe("redact", () => {
  it("redacts known sensitive keys", () => {
    const result = redact({
      apiKey: "costorah_live_abc",
      Authorization: "Bearer costorah_live_abc",
      password: "hunter2",
      userPrompt: "do something",
      modelResponse: "the answer",
      provider: "openai",
    }) as Record<string, unknown>;

    expect(result.apiKey).toBe("***REDACTED***");
    expect(result.Authorization).toBe("***REDACTED***");
    expect(result.password).toBe("***REDACTED***");
    expect(result.userPrompt).toBe("***REDACTED***");
    expect(result.modelResponse).toBe("***REDACTED***");
    expect(result.provider).toBe("openai");
  });

  it("redacts an embedded bearer token in a string", () => {
    const result = redact("auth failed for costorah_live_supersecrettoken123") as string;
    expect(result).not.toContain("supersecrettoken123");
    expect(result).toContain("costorah_live_***REDACTED***");
  });

  it("redacts nested structures", () => {
    const result = redact({
      outer: { apiKey: "costorah_live_x", safe: "ok" },
    }) as { outer: Record<string, unknown> };
    expect(result.outer.apiKey).toBe("***REDACTED***");
    expect(result.outer.safe).toBe("ok");
  });

  it("redacts arrays", () => {
    const result = redact(["costorah_live_abcdef", "plain text"]) as string[];
    expect(result[0]).toBe("costorah_live_***REDACTED***");
    expect(result[1]).toBe("plain text");
  });

  it("passes through non-string, non-container values", () => {
    expect(redact(42)).toBe(42);
    expect(redact(true)).toBe(true);
    expect(redact(null)).toBe(null);
  });
});
