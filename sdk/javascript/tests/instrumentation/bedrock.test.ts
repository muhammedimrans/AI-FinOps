import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

import { BedrockInstrumentor } from "../../src/instrumentation/bedrock.js";
import { createTestClient } from "./testUtils.js";

const nodeRequire = createRequire(import.meta.url);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { BedrockRuntimeClient, ConverseCommand, ConverseStreamCommand }: any = nodeRequire(
  "@aws-sdk/client-bedrock-runtime",
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const basePrototype: any = Object.getPrototypeOf(BedrockRuntimeClient.prototype);
const PRISTINE_SEND = basePrototype.send;

afterEach(() => {
  basePrototype.send = PRISTINE_SEND;
});

function client() {
  return new BedrockRuntimeClient({
    region: "us-east-1",
    credentials: { accessKeyId: "x", secretAccessKey: "y" },
  });
}

function converseResponseFixture(overrides: Record<string, unknown> = {}) {
  return {
    output: { message: { role: "assistant", content: [{ text: "hi" }] } },
    stopReason: "end_turn",
    usage: { inputTokens: 30, outputTokens: 12, totalTokens: 42 },
    ...overrides,
  };
}

describe("BedrockInstrumentor — lifecycle", () => {
  it("instrument()/uninstrument() restore the shared Client.prototype.send", () => {
    const inst = new BedrockInstrumentor();
    inst.instrument();
    expect(basePrototype.send).not.toBe(PRISTINE_SEND);
    inst.uninstrument();
    expect(basePrototype.send).toBe(PRISTINE_SEND);
  });
});

describe("BedrockInstrumentor — Converse capture", () => {
  it("captures usage on a successful converse() call", async () => {
    basePrototype.send = async () => converseResponseFixture();
    const { client: costorahClient, captured } = createTestClient();
    const inst = new BedrockInstrumentor({ client: costorahClient });
    inst.instrument();

    const bedrock = client();
    const result = await bedrock.send(
      new ConverseCommand({ modelId: "anthropic.claude-3-sonnet", messages: [] }),
    );

    expect(result.stopReason).toBe("end_turn");
    await costorahClient.flush();
    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({
      provider: "bedrock",
      model: "anthropic.claude-3-sonnet",
      input_tokens: 30,
      output_tokens: 12,
      total_tokens: 42,
      status: "success",
    });
    inst.uninstrument();
  });

  it("passes non-Converse commands through untouched, without telemetry", async () => {
    let calledWith: unknown;
    basePrototype.send = async (command: unknown) => {
      calledWith = command;
      return { ok: true };
    };
    const { client: costorahClient, captured } = createTestClient();
    const inst = new BedrockInstrumentor({ client: costorahClient });
    inst.instrument();

    const bedrock = client();
    const fakeCommand = { constructor: { name: "ListFoundationModelsCommand" } };
    const result = await bedrock.send(fakeCommand);

    expect(result).toEqual({ ok: true });
    expect(calledWith).toBe(fakeCommand);
    await costorahClient.flush();
    expect(captured).toHaveLength(0);
    inst.uninstrument();
  });

  it("submits an error event and re-throws on failure", async () => {
    basePrototype.send = async () => {
      throw new Error("throttled");
    };
    const { client: costorahClient, captured } = createTestClient();
    const inst = new BedrockInstrumentor({ client: costorahClient });
    inst.instrument();
    const bedrock = client();

    await expect(
      bedrock.send(new ConverseCommand({ modelId: "amazon.titan-text", messages: [] })),
    ).rejects.toThrow("throttled");
    await costorahClient.flush();
    expect(captured[0]).toMatchObject({ status: "error", input_tokens: 0 });
    inst.uninstrument();
  });
});

describe("BedrockInstrumentor — ConverseStream", () => {
  it("only submits telemetry after the stream completes, using metadata usage", async () => {
    async function* streamEvents() {
      yield { contentBlockDelta: { delta: { text: "hi" } } };
      yield { metadata: { usage: { inputTokens: 8, outputTokens: 4, totalTokens: 12 } } };
    }
    basePrototype.send = async () => ({ stream: streamEvents() });
    const { client: costorahClient, captured } = createTestClient();
    const inst = new BedrockInstrumentor({ client: costorahClient });
    inst.instrument();
    const bedrock = client();

    const response = await bedrock.send(
      new ConverseStreamCommand({ modelId: "amazon.titan-text", messages: [] }),
    );

    const seen: unknown[] = [];
    for await (const event of response.stream) {
      seen.push(event);
      await costorahClient.flush();
      expect(captured).toHaveLength(0);
    }

    expect(seen).toHaveLength(2);
    await costorahClient.flush();
    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({ input_tokens: 8, output_tokens: 4, status: "success" });
    inst.uninstrument();
  });
});
