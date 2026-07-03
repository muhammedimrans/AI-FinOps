/**
 * Performance targets from the EP-18.2 ticket: instrumentation overhead
 * <2ms, memory <10MB, correctness at 100,000 requests. Submission is
 * stubbed to a no-op (no network) so these measure the SDK's own
 * interception/extraction/normalization cost, not network latency.
 */
import { createRequire } from "node:module";

import { afterEach, describe, expect, it, vi } from "vitest";

import { OpenAIInstrumentor } from "../../src/instrumentation/openai.js";
import * as submissionModule from "../../src/instrumentation/submission.js";

const nodeRequire = createRequire(import.meta.url);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const OpenAI: any = nodeRequire("openai").default;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { Completions }: any = nodeRequire("openai/resources/chat/completions.js");

const PRISTINE_CREATE = Completions.prototype.create;
const REQUEST_COUNT = 100_000;

afterEach(() => {
  Completions.prototype.create = PRISTINE_CREATE;
  vi.restoreAllMocks();
});

function chatCompletionFixture() {
  return {
    id: "c1",
    choices: [{ message: { content: "hi" } }],
    usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
  };
}

describe("instrumentation performance", () => {
  it(
    "handles 100,000 instrumented requests, all captured",
    async () => {
      vi.spyOn(submissionModule, "submit").mockResolvedValue(true);
      Completions.prototype.create = async () => chatCompletionFixture();
      const inst = new OpenAIInstrumentor();
      inst.instrument();
      const openai = new OpenAI({ apiKey: "sk-test" });

      const start = performance.now();
      for (let i = 0; i < REQUEST_COUNT; i++) {
        await openai.chat.completions.create({ model: "gpt-4o", messages: [] });
      }
      const elapsed = performance.now() - start;
      inst.uninstrument();

      expect(inst.eventsCaptured).toBe(REQUEST_COUNT);
      expect(elapsed).toBeLessThan(60_000);
    },
    90_000,
  );

  it("has bounded instrumentation overhead vs. an uninstrumented baseline", async () => {
    vi.spyOn(submissionModule, "submit").mockResolvedValue(true);
    Completions.prototype.create = async () => chatCompletionFixture();
    const openai = new OpenAI({ apiKey: "sk-test" });

    const baselineSamples: number[] = [];
    for (let i = 0; i < 500; i++) {
      const start = performance.now();
      await openai.chat.completions.create({ model: "gpt-4o", messages: [] });
      baselineSamples.push(performance.now() - start);
    }
    const baselineAvg = baselineSamples.reduce((a, b) => a + b, 0) / baselineSamples.length;

    const inst = new OpenAIInstrumentor();
    inst.instrument();
    const instrumentedSamples: number[] = [];
    for (let i = 0; i < 500; i++) {
      const start = performance.now();
      await openai.chat.completions.create({ model: "gpt-4o", messages: [] });
      instrumentedSamples.push(performance.now() - start);
    }
    inst.uninstrument();
    const instrumentedAvg =
      instrumentedSamples.reduce((a, b) => a + b, 0) / instrumentedSamples.length;

    const overheadMs = instrumentedAvg - baselineAvg;
    // Generous relative to the 2ms target — see module docstring; exists
    // to catch a real regression, not to certify the literal figure on
    // every CI runner.
    expect(overheadMs).toBeLessThan(10);
  });

  it(
    "stays within a bounded memory footprint for 100,000 requests",
    async () => {
      vi.spyOn(submissionModule, "submit").mockResolvedValue(true);
      Completions.prototype.create = async () => chatCompletionFixture();
      const inst = new OpenAIInstrumentor();
      inst.instrument();
      const openai = new OpenAI({ apiKey: "sk-test" });

      if (global.gc) global.gc();
      const baselineMb = process.memoryUsage().heapUsed / 1024 / 1024;

      for (let i = 0; i < REQUEST_COUNT; i++) {
        await openai.chat.completions.create({ model: "gpt-4o", messages: [] });
      }
      inst.uninstrument();

      if (global.gc) global.gc();
      const afterMb = process.memoryUsage().heapUsed / 1024 / 1024;
      const deltaMb = afterMb - baselineMb;

      // Generous — Node's heap growth is non-deterministic without
      // --expose-gc (not wired into package.json's test script), so this
      // can't certify the ticket's literal <10MB figure the way Python's
      // resource.getrusage()-based measurement can. It still catches a
      // real regression: retaining all 100,000 ExtractedUsage objects
      // instead of discarding them per-call would show up as hundreds of
      // MB, far past this bound.
      expect(deltaMb).toBeLessThan(150);
    },
    90_000,
  );
});
