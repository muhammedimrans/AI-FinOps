import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

import { AzureOpenAIInstrumentor } from "../../src/instrumentation/azureOpenai.js";
import { GrokInstrumentor } from "../../src/instrumentation/grok.js";
import { OllamaInstrumentor } from "../../src/instrumentation/ollama.js";
import { resetOpenAIPatchStateForTests } from "../../src/instrumentation/openaiCompatible.js";
import { OpenAIInstrumentor } from "../../src/instrumentation/openai.js";
import { OpenRouterInstrumentor } from "../../src/instrumentation/openrouter.js";
import { createTestClient } from "./testUtils.js";

const nodeRequire = createRequire(import.meta.url);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const OpenAI: any = nodeRequire("openai").default;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { AzureOpenAI }: any = nodeRequire("openai");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { Completions }: any = nodeRequire("openai/resources/chat/completions.js");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { Responses }: any = nodeRequire("openai/resources/responses/responses.js");

const PRISTINE_CHAT_CREATE = Completions.prototype.create;
const PRISTINE_RESPONSES_CREATE = Responses.prototype.create;

afterEach(() => {
  Completions.prototype.create = PRISTINE_CHAT_CREATE;
  Responses.prototype.create = PRISTINE_RESPONSES_CREATE;
  resetOpenAIPatchStateForTests();
});

function chatCompletionFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "chatcmpl-1",
    choices: [{ message: { content: "hi" } }],
    usage: {
      prompt_tokens: 12,
      completion_tokens: 8,
      total_tokens: 20,
      prompt_tokens_details: { cached_tokens: 2 },
    },
    ...overrides,
  };
}

describe("OpenAIInstrumentor — instrument/uninstrument lifecycle", () => {
  it("instrument() is idempotent", () => {
    const inst = new OpenAIInstrumentor();
    inst.instrument();
    inst.instrument();
    expect(inst.isInstrumented()).toBe(true);
    inst.uninstrument();
  });

  it("uninstrument() restores the original create method", () => {
    const inst = new OpenAIInstrumentor();
    inst.instrument();
    expect(Completions.prototype.create).not.toBe(PRISTINE_CHAT_CREATE);
    inst.uninstrument();
    expect(Completions.prototype.create).toBe(PRISTINE_CHAT_CREATE);
  });

  it("double uninstrument() is safe", () => {
    const inst = new OpenAIInstrumentor();
    inst.instrument();
    inst.uninstrument();
    inst.uninstrument();
    expect(Completions.prototype.create).toBe(PRISTINE_CHAT_CREATE);
  });
});

describe("OpenAIInstrumentor — chat completions capture", () => {
  it("captures usage on a successful non-streaming call", async () => {
    Completions.prototype.create = async () => chatCompletionFixture();
    const { client, captured } = createTestClient();
    const inst = new OpenAIInstrumentor({ client });
    inst.instrument();

    const openai = new OpenAI({ apiKey: "sk-test" });
    const result = await openai.chat.completions.create({ model: "gpt-4o", messages: [] });

    expect(result.id).toBe("chatcmpl-1");
    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({
      provider: "openai",
      model: "gpt-4o",
      input_tokens: 12,
      output_tokens: 8,
      total_tokens: 20,
      cached_tokens: 2,
      status: "success",
    });
    inst.uninstrument();
  });

  it("submits a zero-usage error event and re-throws on failure", async () => {
    Completions.prototype.create = async () => {
      throw new Error("upstream failure");
    };
    const { client, captured } = createTestClient();
    const inst = new OpenAIInstrumentor({ client });
    inst.instrument();
    const openai = new OpenAI({ apiKey: "sk-test" });

    await expect(
      openai.chat.completions.create({ model: "gpt-4o", messages: [] }),
    ).rejects.toThrow("upstream failure");

    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({ status: "error", input_tokens: 0, output_tokens: 0 });
    inst.uninstrument();
  });

  it("calculates cost for a known model when the response has no cost field", async () => {
    Completions.prototype.create = async () =>
      chatCompletionFixture({
        usage: { prompt_tokens: 1000, completion_tokens: 500, total_tokens: 1500 },
      });
    const { client, captured } = createTestClient();
    const inst = new OpenAIInstrumentor({ client });
    inst.instrument();
    const openai = new OpenAI({ apiKey: "sk-test" });
    await openai.chat.completions.create({ model: "gpt-4o-mini", messages: [] });

    expect(captured[0]?.cost).toBeCloseTo(0.00045, 8);
    expect(captured[0]?.metadata).toMatchObject({ costEstimated: true });
    inst.uninstrument();
  });

  it("reports cost 0 (not estimated) for an unknown model", async () => {
    Completions.prototype.create = async () => chatCompletionFixture();
    const { client, captured } = createTestClient();
    const inst = new OpenAIInstrumentor({ client });
    inst.instrument();
    const openai = new OpenAI({ apiKey: "sk-test" });
    await openai.chat.completions.create({ model: "not-a-real-model", messages: [] });

    expect(captured[0]?.cost).toBe(0);
    expect(captured[0]?.metadata).toMatchObject({ costEstimated: false });
    inst.uninstrument();
  });

  it("never captures prompt or completion text — only usage metadata", async () => {
    Completions.prototype.create = async () =>
      chatCompletionFixture({ choices: [{ message: { content: "super secret completion" } }] });
    const { client, captured } = createTestClient();
    const inst = new OpenAIInstrumentor({ client });
    inst.instrument();
    const openai = new OpenAI({ apiKey: "sk-test" });
    await openai.chat.completions.create({
      model: "gpt-4o",
      messages: [{ role: "user", content: "super secret prompt" }],
    });

    const serialized = JSON.stringify(captured[0]);
    expect(serialized).not.toContain("super secret");
    inst.uninstrument();
  });
});

describe("OpenAIInstrumentor — Responses API", () => {
  it("captures usage from responses.create", async () => {
    Responses.prototype.create = async () => ({
      id: "resp-1",
      output: [],
      usage: { input_tokens: 5, output_tokens: 3, total_tokens: 8 },
    });
    const { client, captured } = createTestClient();
    const inst = new OpenAIInstrumentor({ client });
    inst.instrument();
    const openai = new OpenAI({ apiKey: "sk-test" });
    await openai.responses.create({ model: "gpt-4.1", input: "Hello" });

    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({ input_tokens: 5, output_tokens: 3, provider: "openai" });
    inst.uninstrument();
  });
});

describe("OpenAIInstrumentor — streaming", () => {
  it("only submits telemetry after the stream completes, using final usage", async () => {
    async function* chunks() {
      yield { choices: [{ delta: { content: "Hel" } }] };
      yield { choices: [{ delta: { content: "lo" } }] };
      yield {
        choices: [],
        usage: { prompt_tokens: 10, completion_tokens: 4, total_tokens: 14 },
      };
    }
    Completions.prototype.create = async () => chunks();
    const { client, captured } = createTestClient();
    const inst = new OpenAIInstrumentor({ client });
    inst.instrument();
    const openai = new OpenAI({ apiKey: "sk-test" });

    const stream = await openai.chat.completions.create({
      model: "gpt-4o",
      messages: [],
      stream: true,
    });

    const collected: unknown[] = [];
    for await (const chunk of stream) {
      collected.push(chunk);
      // Not submitted mid-stream.
      expect(captured).toHaveLength(0);
    }

    expect(collected).toHaveLength(3);
    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({ input_tokens: 10, output_tokens: 4, status: "success" });
    inst.uninstrument();
  });
});

describe("OpenAI-family provider scoping", () => {
  it("only submits telemetry for actively-instrumented providers", async () => {
    Completions.prototype.create = async function (this: { baseURL?: string }) {
      return chatCompletionFixture();
    };
    const openaiClient = createTestClient();
    const azureClient = createTestClient();
    const openaiInst = new OpenAIInstrumentor({ client: openaiClient.client });
    const azureInst = new AzureOpenAIInstrumentor({ client: azureClient.client });

    // Only OpenAI is instrumented — Azure traffic through the same shared
    // patch must not be captured by anyone.
    openaiInst.instrument();
    const azure = new AzureOpenAI({
      apiKey: "sk-test",
      endpoint: "https://foo.openai.azure.com",
      apiVersion: "2024-02-01",
    });
    await azure.chat.completions.create({ model: "gpt-4o", messages: [] });
    expect(openaiClient.captured).toHaveLength(0);
    expect(azureClient.captured).toHaveLength(0);

    // Once Azure is also instrumented, its own traffic is captured — and
    // only by the Azure instrumentor.
    azureInst.instrument();
    await azure.chat.completions.create({ model: "gpt-4o", messages: [] });
    expect(azureClient.captured).toHaveLength(1);
    expect(azureClient.captured[0]).toMatchObject({ provider: "azure_openai" });
    expect(openaiClient.captured).toHaveLength(0);

    openaiInst.uninstrument();
    azureInst.uninstrument();
  });

  it("sibling uninstrument() does not break another active family member", async () => {
    const fixtureCreate = async () => chatCompletionFixture();
    Completions.prototype.create = fixtureCreate;
    const openaiClient = createTestClient();
    const routerClient = createTestClient();
    const openaiInst = new OpenAIInstrumentor({ client: openaiClient.client });
    const routerInst = new OpenRouterInstrumentor({ client: routerClient.client });

    openaiInst.instrument();
    routerInst.instrument();
    routerInst.uninstrument();

    // OpenAI instrumentor must still work after the sibling uninstrumented.
    const openai = new OpenAI({ apiKey: "sk-test" });
    await openai.chat.completions.create({ model: "gpt-4o", messages: [] });
    expect(openaiClient.captured).toHaveLength(1);

    openaiInst.uninstrument();
    expect(Completions.prototype.create).toBe(fixtureCreate);
  });

  it("detects Ollama and Grok by baseURL host hints", async () => {
    Completions.prototype.create = async () => chatCompletionFixture();
    const ollamaClient = createTestClient();
    const grokClient = createTestClient();
    const ollamaInst = new OllamaInstrumentor({ client: ollamaClient.client });
    const grokInst = new GrokInstrumentor({ client: grokClient.client });
    ollamaInst.instrument();
    grokInst.instrument();

    const ollama = new OpenAI({ apiKey: "ollama", baseURL: "http://localhost:11434/v1" });
    await ollama.chat.completions.create({ model: "llama3", messages: [] });
    expect(ollamaClient.captured).toHaveLength(1);
    expect(ollamaClient.captured[0]).toMatchObject({ provider: "ollama" });

    const grok = new OpenAI({ apiKey: "xai", baseURL: "https://api.x.ai/v1" });
    await grok.chat.completions.create({ model: "grok-2", messages: [] });
    expect(grokClient.captured).toHaveLength(1);
    expect(grokClient.captured[0]).toMatchObject({ provider: "grok" });

    ollamaInst.uninstrument();
    grokInst.uninstrument();
  });
});
