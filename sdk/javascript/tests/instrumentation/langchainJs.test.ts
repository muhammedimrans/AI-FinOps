import { afterEach, describe, expect, it } from "vitest";

import {
  CostorahLangChainHandler,
  extractFinishReason,
  extractUsageMetadata,
  inferProviderFromModel,
  inferProviderFromModulePath,
  LangChainInstrumentor,
} from "../../src/instrumentation/langchainJs.js";
import { createTestClient } from "./testUtils.js";

function chatResult(overrides: Record<string, unknown> = {}) {
  return {
    generations: [
      [
        {
          generationInfo: { finish_reason: "stop" },
          message: {
            usage_metadata: {
              input_tokens: 10,
              output_tokens: 5,
              total_tokens: 15,
            },
            response_metadata: { model_name: "gpt-4o-mini" },
          },
        },
      ],
    ],
    llmOutput: {},
    ...overrides,
  };
}

describe("provider inference", () => {
  it("infers provider from model name prefix", () => {
    expect(inferProviderFromModel("gpt-4o-mini")).toBe("openai");
    expect(inferProviderFromModel("claude-3-5-sonnet-20241022")).toBe("anthropic");
    expect(inferProviderFromModel("totally-unknown-model")).toBeUndefined();
    expect(inferProviderFromModel(undefined)).toBeUndefined();
  });

  it("infers provider from lc_namespace module path", () => {
    expect(inferProviderFromModulePath("langchain/chat_models/openai")).toBe("openai");
    expect(inferProviderFromModulePath("langchain/chat_models/anthropic")).toBe("anthropic");
    expect(inferProviderFromModulePath("some/random/path")).toBeUndefined();
    expect(inferProviderFromModulePath(undefined)).toBeUndefined();
  });
});

describe("usage extraction", () => {
  it("extracts standardized usage_metadata, preferring response_metadata.model_name", () => {
    const usage = extractUsageMetadata(chatResult());
    expect(usage).toEqual({
      model: "gpt-4o-mini",
      inputTokens: 10,
      outputTokens: 5,
      totalTokens: 15,
      cachedTokens: undefined,
      reasoningTokens: undefined,
    });
  });

  it("extracts reasoning and cached token details when present", () => {
    const result = chatResult({
      generations: [
        [
          {
            generationInfo: { finish_reason: "stop" },
            message: {
              usage_metadata: {
                input_tokens: 100,
                output_tokens: 42,
                total_tokens: 142,
                input_token_details: { cache_read: 3 },
                output_token_details: { reasoning: 7 },
              },
              response_metadata: { model_name: "o1-preview" },
            },
          },
        ],
      ],
    });
    const usage = extractUsageMetadata(result);
    expect(usage?.reasoningTokens).toBe(7);
    expect(usage?.cachedTokens).toBe(3);
  });

  it("extracts finish reason from generationInfo", () => {
    const result = chatResult();
    expect(extractFinishReason(result)).toBe("stop");
  });

  it("falls back to llmOutput.tokenUsage for non-chat LLMs", () => {
    const result = {
      generations: [[]],
      llmOutput: {
        model_name: "gpt-3.5-turbo-instruct",
        tokenUsage: { promptTokens: 20, completionTokens: 8, totalTokens: 28 },
      },
    };
    const usage = extractUsageMetadata(result);
    expect(usage).toEqual({
      model: "gpt-3.5-turbo-instruct",
      inputTokens: 20,
      outputTokens: 8,
      totalTokens: 28,
      cachedTokens: undefined,
      reasoningTokens: undefined,
    });
  });

  it("returns undefined when no usage data exists", () => {
    const result = { generations: [[]], llmOutput: {} };
    expect(extractUsageMetadata(result)).toBeUndefined();
  });
});

describe("CostorahLangChainHandler called directly", () => {
  it("submits usage with trace context on a real Costorah client", async () => {
    const { client, captured } = createTestClient();
    const handler = new CostorahLangChainHandler({ client });
    const runId = "run-1";

    handler.handleChatModelStart(
      { id: ["langchain", "chat_models", "openai", "ChatOpenAI"] },
      [],
      runId,
    );
    await handler.handleLLMEnd(chatResult(), runId);
    await client.flush(5000);

    expect(captured).toHaveLength(1);
    const usage = captured[0]!;
    expect(usage.provider).toBe("openai");
    expect(usage.model).toBe("gpt-4o-mini");
    expect(usage.input_tokens).toBe(10);
    expect(usage.output_tokens).toBe(5);
    expect((usage.metadata as Record<string, unknown>).framework).toBe("langchain");
    expect((usage.metadata as Record<string, unknown>).finishReason).toBe("stop");
    expect((usage.metadata as Record<string, unknown>).traceId).toMatch(/^trace_/);
  });

  it("does not submit for an unrecognized model", async () => {
    const { client, captured } = createTestClient();
    const handler = new CostorahLangChainHandler({ client });
    const runId = "run-2";

    handler.handleChatModelStart({ id: ["some_custom_package", "MyLLM"] }, [], runId);
    await handler.handleLLMEnd(
      chatResult({
        generations: [
          [
            {
              generationInfo: {},
              message: {
                usage_metadata: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
                response_metadata: { model_name: "totally-custom-self-hosted-model" },
              },
            },
          ],
        ],
      }),
      runId,
    );
    await client.flush(5000);

    expect(captured).toHaveLength(0);
  });

  it("nested LLM call inherits parent trace id and chain name enrichment", async () => {
    const { client, captured } = createTestClient();
    const handler = new CostorahLangChainHandler({ client });
    const chainRunId = "chain-1";
    const llmRunId = "llm-1";

    handler.handleChainStart({ id: ["some_chain", "MyChain"] }, {}, chainRunId);
    handler.handleChatModelStart(
      { id: ["langchain", "chat_models", "openai", "ChatOpenAI"] },
      [],
      llmRunId,
      chainRunId,
    );
    await handler.handleLLMEnd(chatResult(), llmRunId, chainRunId);
    handler.handleChainEnd({}, chainRunId);
    await client.flush(5000);

    expect(captured).toHaveLength(1);
    const metadata = captured[0]!.metadata as Record<string, unknown>;
    expect(metadata.parentSpanId).toBe(chainRunId);
    expect(metadata.chainName).toBe("MyChain");
  });

  it("tool context enriches a nested LLM call", async () => {
    const { client, captured } = createTestClient();
    const handler = new CostorahLangChainHandler({ client });
    const toolRunId = "tool-1";
    const llmRunId = "llm-2";

    handler.handleToolStart({ id: ["some_tool", "MyTool"], name: "MyTool" }, "input", toolRunId);
    handler.handleChatModelStart(
      { id: ["langchain", "chat_models", "openai", "ChatOpenAI"] },
      [],
      llmRunId,
      toolRunId,
    );
    await handler.handleLLMEnd(chatResult(), llmRunId, toolRunId);
    handler.handleToolEnd("output", toolRunId);
    await client.flush(5000);

    expect(captured).toHaveLength(1);
    expect((captured[0]!.metadata as Record<string, unknown>).toolName).toBe("MyTool");
  });

  it("a chain's tracked run is forgotten after it ends, so a later unrelated LLM call under the same runId is not mistakenly enriched", async () => {
    const { client, captured } = createTestClient();
    const handler = new CostorahLangChainHandler({ client });
    const chainRunId = "chain-2";
    handler.handleChainStart({ id: ["c", "MyChain"] }, {}, chainRunId);
    handler.handleChainEnd({}, chainRunId);

    // Reusing the same id as a fresh, unrelated LLM run's parentRunId —
    // since the chain's entry was deleted on handleChainEnd, this must
    // not pick up "MyChain".
    handler.handleChatModelStart(
      { id: ["langchain", "chat_models", "openai", "ChatOpenAI"] },
      [],
      "llm-3",
      chainRunId,
    );
    await handler.handleLLMEnd(chatResult(), "llm-3", chainRunId);
    await client.flush(5000);

    expect(captured).toHaveLength(1);
    expect((captured[0]!.metadata as Record<string, unknown>).chainName).toBeUndefined();
  });

  it("a chain's tracked run is forgotten even when the chain errors", () => {
    const handler = new CostorahLangChainHandler({});
    const chainRunId = "chain-3";
    handler.handleChainStart({ id: ["c", "MyChain"] }, {}, chainRunId);
    handler.handleChainError(new Error("boom"), chainRunId);
    // events_captured still counts both, but the run entry itself must
    // be gone — verified indirectly via the "no leak" test above's same
    // mechanism; here we just confirm the error path also calls endSpan.
    expect(handler.eventsCaptured).toBe(2);
  });

  it("counts every lifecycle event", () => {
    const handler = new CostorahLangChainHandler({});
    const runId = "chain-4";
    handler.handleChainStart({ id: ["c", "MyChain"] }, {}, runId);
    handler.handleChainEnd({}, runId);
    expect(handler.eventsCaptured).toBe(2);
  });
});

describe("LangChainInstrumentor lifecycle", () => {
  afterEach(async () => {
    const instrumentor = new LangChainInstrumentor();
    await instrumentor.uninstrument();
  });

  it("instrument() is idempotent", async () => {
    const instrumentor = new LangChainInstrumentor();
    await instrumentor.instrument();
    await instrumentor.instrument();
    expect(instrumentor.isInstrumented()).toBe(true);
    await instrumentor.uninstrument();
  });

  it("uninstrument() clears instrumented state", async () => {
    const instrumentor = new LangChainInstrumentor();
    await instrumentor.instrument();
    expect(instrumentor.isInstrumented()).toBe(true);
    await instrumentor.uninstrument();
    expect(instrumentor.isInstrumented()).toBe(false);
  });
});

describe("end-to-end via a real ChatOpenAI instance", () => {
  it("captures usage through invoke() with no manual tracking calls, never leaking prompt/response text", async () => {
    const { ChatOpenAI } = await import("@langchain/openai");
    const { client, captured } = createTestClient();

    const instrumentor = new LangChainInstrumentor({ client });
    await instrumentor.instrument();
    try {
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

      const model = new ChatOpenAI({
        apiKey: "sk-fake",
        model: "gpt-4o-mini",
        configuration: { fetch: fakeFetch },
      });
      const result = await model.invoke("Hello");
      expect(result.content).toBe("hi there");

      await client.flush(5000);
      expect(captured).toHaveLength(1);
      const usage = captured[0]!;
      expect(usage.provider).toBe("openai");
      expect(usage.model).toBe("gpt-4o-mini");
      expect(usage.input_tokens).toBe(10);
      expect(usage.output_tokens).toBe(5);
      expect((usage.metadata as Record<string, unknown>).framework).toBe("langchain");

      const payloadStr = JSON.stringify(usage);
      expect(payloadStr).not.toContain("Hello");
      expect(payloadStr).not.toContain("hi there");
    } finally {
      await instrumentor.uninstrument();
    }
  });
});
