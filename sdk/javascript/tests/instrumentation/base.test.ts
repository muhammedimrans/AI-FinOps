import { describe, expect, it } from "vitest";

import { BaseInstrumentor, makeExtractedUsage } from "../../src/instrumentation/base.js";
import type { ExtractedUsage } from "../../src/instrumentation/base.js";

class FakeInstrumentor extends BaseInstrumentor {
  readonly name = "fake";
  applyCalls = 0;
  removeCalls = 0;

  extractUsage(): Record<string, unknown> {
    return {};
  }

  normalize(): ExtractedUsage {
    return makeExtractedUsage({ provider: "fake", model: "m", requestId: "r" });
  }

  protected applyPatches(): void {
    this.applyCalls += 1;
  }

  protected removePatches(): void {
    this.removeCalls += 1;
  }

  triggerCapture(): void {
    this.recordCaptured();
  }
}

describe("BaseInstrumentor lifecycle", () => {
  it("instrument() applies patches exactly once", () => {
    const inst = new FakeInstrumentor();
    expect(inst.isInstrumented()).toBe(false);
    inst.instrument();
    expect(inst.isInstrumented()).toBe(true);
    expect(inst.applyCalls).toBe(1);
  });

  it("double instrument() is a no-op", () => {
    const inst = new FakeInstrumentor();
    inst.instrument();
    inst.instrument();
    expect(inst.applyCalls).toBe(1);
  });

  it("uninstrument() restores exactly once", () => {
    const inst = new FakeInstrumentor();
    inst.instrument();
    inst.uninstrument();
    expect(inst.isInstrumented()).toBe(false);
    expect(inst.removeCalls).toBe(1);
  });

  it("uninstrument() before instrument() is a no-op", () => {
    const inst = new FakeInstrumentor();
    inst.uninstrument();
    expect(inst.removeCalls).toBe(0);
  });

  it("double uninstrument() only restores once", () => {
    const inst = new FakeInstrumentor();
    inst.instrument();
    inst.uninstrument();
    inst.uninstrument();
    expect(inst.removeCalls).toBe(1);
  });

  it("disabled instrumentor never patches", () => {
    const inst = new FakeInstrumentor({ enabled: false });
    inst.instrument();
    expect(inst.isInstrumented()).toBe(false);
    expect(inst.applyCalls).toBe(0);
  });

  it("tracks eventsCaptured", () => {
    const inst = new FakeInstrumentor();
    expect(inst.eventsCaptured).toBe(0);
    inst.triggerCapture();
    inst.triggerCapture();
    expect(inst.eventsCaptured).toBe(2);
  });

  it("re-instrument after uninstrument re-applies patches", () => {
    const inst = new FakeInstrumentor();
    inst.instrument();
    inst.uninstrument();
    inst.instrument();
    expect(inst.applyCalls).toBe(2);
    expect(inst.isInstrumented()).toBe(true);
  });
});

describe("makeExtractedUsage", () => {
  it("fills in defaults", () => {
    const usage = makeExtractedUsage({ provider: "openai", model: "gpt-4.1", requestId: "r1" });
    expect(usage.inputTokens).toBe(0);
    expect(usage.outputTokens).toBe(0);
    expect(usage.cachedTokens).toBeUndefined();
    expect(usage.totalTokens).toBeUndefined();
    expect(usage.cost).toBe(0);
    expect(usage.currency).toBe("USD");
    expect(usage.status).toBe("success");
    expect(usage.metadata).toEqual({});
    expect(usage.timestamp).toBeInstanceOf(Date);
  });

  it("overrides defaults with partial fields", () => {
    const usage = makeExtractedUsage({
      provider: "anthropic",
      model: "claude-sonnet-4",
      requestId: "r2",
      inputTokens: 100,
      outputTokens: 50,
      cost: 0.01,
      status: "error",
    });
    expect(usage.inputTokens).toBe(100);
    expect(usage.outputTokens).toBe(50);
    expect(usage.cost).toBe(0.01);
    expect(usage.status).toBe("error");
  });
});
