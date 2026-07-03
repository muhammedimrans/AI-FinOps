import { describe, expect, it } from "vitest";

import { InstrumentationError } from "../../src/instrumentation/base.js";
import { GeminiInstrumentor } from "../../src/instrumentation/google.js";
import { createTestClient } from "./testUtils.js";

function fakeGeminiClient() {
  const calls: { method: string; params: unknown }[] = [];
  return {
    calls,
    models: {
      generateContent: async (params: unknown) => {
        calls.push({ method: "generateContent", params });
        return {
          candidates: [{ content: { parts: [{ text: "hi" }] } }],
          usageMetadata: {
            promptTokenCount: 18,
            candidatesTokenCount: 6,
            cachedContentTokenCount: 2,
            totalTokenCount: 24,
          },
        };
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      generateContentStream: async (params: unknown): Promise<any> => {
        calls.push({ method: "generateContentStream", params });
        async function* gen() {
          yield { usageMetadata: { promptTokenCount: 18, candidatesTokenCount: 1 } };
          yield { usageMetadata: { promptTokenCount: 18, candidatesTokenCount: 6 } };
        }
        return gen();
      },
    },
  };
}

describe("GeminiInstrumentor — client-scoped lifecycle", () => {
  it("requires a client instance — zero-arg instrument() throws", () => {
    const inst = new GeminiInstrumentor();
    expect(() => inst.instrument()).toThrow(InstrumentationError);
  });

  it("instrument(client)/uninstrument() wrap and restore only the given instance", () => {
    const target = fakeGeminiClient();
    const originalGenerateContent = target.models.generateContent;
    const inst = new GeminiInstrumentor();
    inst.instrument(target as never);
    expect(target.models.generateContent).not.toBe(originalGenerateContent);
    inst.uninstrument();
    expect(target.models.generateContent).toBe(originalGenerateContent);
  });

  it("double instrument(client) is a no-op", () => {
    const target = fakeGeminiClient();
    const inst = new GeminiInstrumentor();
    inst.instrument(target as never);
    const wrapped = target.models.generateContent;
    inst.instrument(target as never);
    expect(target.models.generateContent).toBe(wrapped);
    inst.uninstrument();
  });
});

describe("GeminiInstrumentor — capture", () => {
  it("captures usage on a successful generateContent() call", async () => {
    const target = fakeGeminiClient();
    const { client, captured } = createTestClient();
    const inst = new GeminiInstrumentor({ client });
    inst.instrument(target as never);

    await target.models.generateContent({ model: "gemini-1.5-pro", contents: "Hello" });

    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({
      provider: "google",
      model: "gemini-1.5-pro",
      input_tokens: 18,
      output_tokens: 6,
      cached_tokens: 2,
      total_tokens: 24,
      status: "success",
    });
    inst.uninstrument();
  });

  it("submits an error event and re-throws on failure", async () => {
    const target = fakeGeminiClient();
    target.models.generateContent = async () => {
      throw new Error("quota exceeded");
    };
    const { client, captured } = createTestClient();
    const inst = new GeminiInstrumentor({ client });
    inst.instrument(target as never);

    await expect(
      target.models.generateContent({ model: "gemini-1.5-pro", contents: "Hi" }),
    ).rejects.toThrow("quota exceeded");
    expect(captured[0]).toMatchObject({ status: "error", input_tokens: 0 });
    inst.uninstrument();
  });

  it("streaming: only submits after completion, using the last chunk's usage", async () => {
    const target = fakeGeminiClient();
    const { client, captured } = createTestClient();
    const inst = new GeminiInstrumentor({ client });
    inst.instrument(target as never);

    const stream = await target.models.generateContentStream({
      model: "gemini-1.5-pro",
      contents: "Hi",
    });
    const seen: unknown[] = [];
    for await (const chunk of stream) {
      seen.push(chunk);
      expect(captured).toHaveLength(0);
    }

    expect(seen).toHaveLength(2);
    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({ input_tokens: 18, output_tokens: 6, status: "success" });
    inst.uninstrument();
  });
});
