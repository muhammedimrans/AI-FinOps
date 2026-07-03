import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

import { MistralInstrumentor } from "../../src/instrumentation/mistral.js";
import { createTestClient } from "./testUtils.js";

const nodeRequire = createRequire(import.meta.url);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { Mistral }: any = nodeRequire("@mistralai/mistralai");

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const chatProto: any = Object.getPrototypeOf(new Mistral({ apiKey: "probe" }).chat);
const PRISTINE_COMPLETE = chatProto.complete;
const PRISTINE_STREAM = chatProto.stream;

afterEach(() => {
  chatProto.complete = PRISTINE_COMPLETE;
  chatProto.stream = PRISTINE_STREAM;
});

function chatCompletionFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "cmpl-1",
    choices: [{ message: { content: "hi" } }],
    usage: { promptTokens: 15, completionTokens: 7, totalTokens: 22 },
    ...overrides,
  };
}

describe("MistralInstrumentor — lifecycle", () => {
  it("instrument()/uninstrument() restore the shared Chat prototype", () => {
    const inst = new MistralInstrumentor();
    inst.instrument();
    expect(chatProto.complete).not.toBe(PRISTINE_COMPLETE);
    inst.instrument();
    inst.uninstrument();
    expect(chatProto.complete).toBe(PRISTINE_COMPLETE);
    inst.uninstrument();
  });

  it("patching via the probe intercepts a separately-constructed client", async () => {
    chatProto.complete = async () => chatCompletionFixture();
    const { client, captured } = createTestClient();
    const inst = new MistralInstrumentor({ client });
    inst.instrument();

    const independentClient = new Mistral({ apiKey: "another-key" });
    await independentClient.chat.complete({ model: "mistral-large-latest", messages: [] });

    await client.flush();
    expect(captured).toHaveLength(1);
    await client.flush();
    expect(captured[0]).toMatchObject({ provider: "mistral", input_tokens: 15, output_tokens: 7 });
    inst.uninstrument();
  });
});

describe("MistralInstrumentor — capture", () => {
  it("submits an error event and re-throws on failure", async () => {
    chatProto.complete = async () => {
      throw new Error("bad request");
    };
    const { client, captured } = createTestClient();
    const inst = new MistralInstrumentor({ client });
    inst.instrument();
    const mistral = new Mistral({ apiKey: "x" });

    await expect(
      mistral.chat.complete({ model: "mistral-large-latest", messages: [] }),
    ).rejects.toThrow("bad request");
    await client.flush();
    expect(captured[0]).toMatchObject({ status: "error", input_tokens: 0 });
    inst.uninstrument();
  });

  it("computes cost for a known model", async () => {
    chatProto.complete = async () =>
      chatCompletionFixture({ usage: { promptTokens: 1000, completionTokens: 1000 } });
    const { client, captured } = createTestClient();
    const inst = new MistralInstrumentor({ client });
    inst.instrument();
    const mistral = new Mistral({ apiKey: "x" });
    await mistral.chat.complete({ model: "mistral-small-latest", messages: [] });

    // 1000 * 0.0000001 + 1000 * 0.0000003 = 0.0004
    await client.flush();
    expect(captured[0]?.cost).toBeCloseTo(0.0004, 8);
    inst.uninstrument();
  });
});

describe("MistralInstrumentor — streaming", () => {
  it("aggregates usage from the last chunk that carries it", async () => {
    async function* events() {
      yield { data: { choices: [{ delta: { content: "he" } }] } };
      yield {
        data: {
          choices: [],
          usage: { promptTokens: 9, completionTokens: 3, totalTokens: 12 },
        },
      };
    }
    chatProto.stream = async () => events();
    const { client, captured } = createTestClient();
    const inst = new MistralInstrumentor({ client });
    inst.instrument();
    const mistral = new Mistral({ apiKey: "x" });

    const stream = await mistral.chat.stream({ model: "mistral-large-latest", messages: [] });
    const seen: unknown[] = [];
    for await (const event of stream) {
      seen.push(event);
      await client.flush();
      expect(captured).toHaveLength(0);
    }

    expect(seen).toHaveLength(2);
    await client.flush();
    expect(captured).toHaveLength(1);
    await client.flush();
    expect(captured[0]).toMatchObject({ input_tokens: 9, output_tokens: 3, status: "success" });
    inst.uninstrument();
  });
});
