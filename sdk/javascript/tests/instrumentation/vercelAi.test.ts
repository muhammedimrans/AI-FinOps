import { describe, expect, it } from "vitest";

import {
  inferProviderFromVercelProviderId,
  VercelAIInstrumentor,
} from "../../src/instrumentation/vercelAi.js";
import { createTestClient } from "./testUtils.js";

describe("inferProviderFromVercelProviderId", () => {
  it("maps known Vercel AI SDK provider ids to SUPPORTED_PROVIDERS members", () => {
    expect(inferProviderFromVercelProviderId("openai.responses")).toBe("openai");
    expect(inferProviderFromVercelProviderId("openai.chat")).toBe("openai");
    expect(inferProviderFromVercelProviderId("anthropic.messages")).toBe("anthropic");
    expect(inferProviderFromVercelProviderId("google.generative-ai")).toBe("google");
  });

  it("returns undefined for an unrecognized provider id", () => {
    expect(inferProviderFromVercelProviderId("totally-custom.chat")).toBeUndefined();
  });
});

function fakeModel(overrides: Partial<{ provider: string; modelId: string }> = {}) {
  return {
    specificationVersion: "v2" as const,
    provider: overrides.provider ?? "openai.chat",
    modelId: overrides.modelId ?? "gpt-4o-mini",
  };
}

describe("VercelAIInstrumentor.middleware() called directly", () => {
  it("wrapGenerate submits usage with correct provider/model/cost, awaited before resolving", async () => {
    const { client, captured } = createTestClient();
    const instrumentor = new VercelAIInstrumentor({ client });
    instrumentor.instrument();

    const middleware = instrumentor.middleware();
    const model = fakeModel();
    const result = await middleware.wrapGenerate!({
      doGenerate: async () => ({
        usage: { inputTokens: 10, outputTokens: 5, totalTokens: 15 },
        finishReason: "stop",
      }),
      doStream: async () => {
        throw new Error("not used");
      },
      params: {},
      model,
    });
    expect(result.finishReason).toBe("stop");

    await client.flush(5000);
    expect(captured).toHaveLength(1);
    const usage = captured[0]!;
    expect(usage.provider).toBe("openai");
    expect(usage.model).toBe("gpt-4o-mini");
    expect(usage.input_tokens).toBe(10);
    expect(usage.output_tokens).toBe(5);
    expect(usage.cost).toBeGreaterThan(0);
    expect((usage.metadata as Record<string, unknown>).framework).toBe("vercel-ai-sdk");
    expect((usage.metadata as Record<string, unknown>).finishReason).toBe("stop");
    expect(instrumentor.eventsCaptured).toBe(1);
  });

  it("does not submit for an unrecognized provider id", async () => {
    const { client, captured } = createTestClient();
    const instrumentor = new VercelAIInstrumentor({ client });
    instrumentor.instrument();

    const middleware = instrumentor.middleware();
    await middleware.wrapGenerate!({
      doGenerate: async () => ({
        usage: { inputTokens: 1, outputTokens: 1, totalTokens: 2 },
      }),
      doStream: async () => {
        throw new Error("not used");
      },
      params: {},
      model: fakeModel({ provider: "totally-custom.chat" }),
    });

    await client.flush(5000);
    expect(captured).toHaveLength(0);
  });

  it("still records the failed call and rethrows when doGenerate throws", async () => {
    const instrumentor = new VercelAIInstrumentor({});
    instrumentor.instrument();
    const middleware = instrumentor.middleware();

    await expect(
      middleware.wrapGenerate!({
        doGenerate: async () => {
          throw new Error("boom");
        },
        doStream: async () => {
          throw new Error("not used");
        },
        params: {},
        model: fakeModel(),
      }),
    ).rejects.toThrow("boom");

    expect(instrumentor.eventsCaptured).toBe(1);
  });

  it("captures reasoning and cached token details when present", async () => {
    const { client, captured } = createTestClient();
    const instrumentor = new VercelAIInstrumentor({ client });
    instrumentor.instrument();

    const middleware = instrumentor.middleware();
    await middleware.wrapGenerate!({
      doGenerate: async () => ({
        usage: {
          inputTokens: 100,
          outputTokens: 42,
          totalTokens: 142,
          reasoningTokens: 7,
          cachedInputTokens: 3,
        },
        finishReason: "stop",
      }),
      doStream: async () => {
        throw new Error("not used");
      },
      params: {},
      model: fakeModel({ modelId: "o1-preview" }),
    });

    await client.flush(5000);
    expect(captured).toHaveLength(1);
    const metadata = captured[0]!.metadata as Record<string, unknown>;
    expect(metadata.reasoningTokens).toBe(7);
    expect(metadata.cachedTokens).toBe(3);
  });
});

describe("VercelAIInstrumentor lifecycle", () => {
  it("wrapModel returns the original model unchanged before instrument()", () => {
    const instrumentor = new VercelAIInstrumentor({});
    const model = fakeModel();
    expect(instrumentor.wrapModel(model)).toBe(model);
  });

  it("isInstrumented reflects instrument()/uninstrument() state", () => {
    const instrumentor = new VercelAIInstrumentor({});
    expect(instrumentor.isInstrumented()).toBe(false);
    instrumentor.instrument();
    expect(instrumentor.isInstrumented()).toBe(true);
    instrumentor.uninstrument();
    expect(instrumentor.isInstrumented()).toBe(false);
  });
});

describe("end-to-end via a real @ai-sdk/openai chat model and ai's generateText", () => {
  it("captures usage through generateText() with no manual tracking calls, never leaking prompt/response text", async () => {
    const { createOpenAI } = await import("@ai-sdk/openai");
    const { generateText } = await import("ai");
    const { client, captured } = createTestClient();

    const instrumentor = new VercelAIInstrumentor({ client });
    instrumentor.instrument();

    const fakeFetch = async () =>
      new Response(
        JSON.stringify({
          id: "c1",
          object: "chat.completion",
          created: 0,
          model: "gpt-4o-mini",
          choices: [
            {
              index: 0,
              message: { role: "assistant", content: "hi there" },
              finish_reason: "stop",
            },
          ],
          usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );

    const openai = createOpenAI({ apiKey: "sk-fake", fetch: fakeFetch as unknown as typeof fetch });
    const rawModel = openai.chat("gpt-4o-mini");
    const model = instrumentor.wrapModel(rawModel);

    const result = await generateText({ model, prompt: "Hello" });
    expect(result.text).toBe("hi there");

    await client.flush(5000);
    expect(captured).toHaveLength(1);
    const usage = captured[0]!;
    expect(usage.provider).toBe("openai");
    expect(usage.model).toBe("gpt-4o-mini");
    expect(usage.input_tokens).toBe(10);
    expect(usage.output_tokens).toBe(5);
    expect((usage.metadata as Record<string, unknown>).framework).toBe("vercel-ai-sdk");

    const payloadStr = JSON.stringify(usage);
    expect(payloadStr).not.toContain("Hello");
    expect(payloadStr).not.toContain("hi there");
  });
});
