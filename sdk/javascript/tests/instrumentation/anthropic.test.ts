import { createRequire } from "node:module";

import { afterEach, describe, expect, it } from "vitest";

import { AnthropicInstrumentor } from "../../src/instrumentation/anthropic.js";
import { createTestClient } from "./testUtils.js";

const nodeRequire = createRequire(import.meta.url);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Anthropic: any = nodeRequire("@anthropic-ai/sdk").default;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { Messages }: any = nodeRequire("@anthropic-ai/sdk/resources/messages.js");

const PRISTINE_CREATE = Messages.prototype.create;

afterEach(() => {
  Messages.prototype.create = PRISTINE_CREATE;
});

function messageFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "msg_1",
    content: [{ type: "text", text: "hi" }],
    usage: { input_tokens: 20, output_tokens: 10, cache_read_input_tokens: 5 },
    ...overrides,
  };
}

describe("AnthropicInstrumentor — lifecycle", () => {
  it("instrument()/uninstrument() are idempotent and restore the original", () => {
    const inst = new AnthropicInstrumentor();
    inst.instrument();
    inst.instrument();
    expect(inst.isInstrumented()).toBe(true);
    inst.uninstrument();
    inst.uninstrument();
    expect(Messages.prototype.create).toBe(PRISTINE_CREATE);
  });
});

describe("AnthropicInstrumentor — non-streaming capture", () => {
  it("captures usage on success", async () => {
    Messages.prototype.create = async () => messageFixture();
    const { client, captured } = createTestClient();
    const inst = new AnthropicInstrumentor({ client });
    inst.instrument();

    const anthropic = new Anthropic({ apiKey: "sk-ant-test" });
    await anthropic.messages.create({
      model: "claude-sonnet-4",
      max_tokens: 100,
      messages: [],
    });

    await client.flush();
    expect(captured).toHaveLength(1);
    await client.flush();
    expect(captured[0]).toMatchObject({
      provider: "anthropic",
      model: "claude-sonnet-4",
      input_tokens: 20,
      output_tokens: 10,
      cached_tokens: 5,
      status: "success",
    });
    inst.uninstrument();
  });

  it("submits an error event and re-throws on failure", async () => {
    Messages.prototype.create = async () => {
      throw new Error("rate limited");
    };
    const { client, captured } = createTestClient();
    const inst = new AnthropicInstrumentor({ client });
    inst.instrument();
    const anthropic = new Anthropic({ apiKey: "sk-ant-test" });

    await expect(
      anthropic.messages.create({ model: "claude-sonnet-4", max_tokens: 100, messages: [] }),
    ).rejects.toThrow("rate limited");
    await client.flush();
    expect(captured[0]).toMatchObject({ status: "error", input_tokens: 0 });
    inst.uninstrument();
  });

  it("never captures message content", async () => {
    Messages.prototype.create = async () =>
      messageFixture({ content: [{ type: "text", text: "top secret reply" }] });
    const { client, captured } = createTestClient();
    const inst = new AnthropicInstrumentor({ client });
    inst.instrument();
    const anthropic = new Anthropic({ apiKey: "sk-ant-test" });
    await anthropic.messages.create({
      model: "claude-sonnet-4",
      max_tokens: 100,
      messages: [{ role: "user", content: "top secret prompt" }],
    });
    await client.flush();
    expect(JSON.stringify(captured[0])).not.toContain("top secret");
    inst.uninstrument();
  });
});

describe("AnthropicInstrumentor — streaming", () => {
  it("aggregates usage across message_start/message_delta events", async () => {
    async function* events() {
      yield { type: "message_start", message: { usage: { input_tokens: 20, output_tokens: 0 } } };
      yield { type: "content_block_delta", delta: { text: "hi" } };
      yield { type: "message_delta", usage: { output_tokens: 10 } };
    }
    Messages.prototype.create = async () => events();
    const { client, captured } = createTestClient();
    const inst = new AnthropicInstrumentor({ client });
    inst.instrument();
    const anthropic = new Anthropic({ apiKey: "sk-ant-test" });

    const stream = await anthropic.messages.create({
      model: "claude-sonnet-4",
      max_tokens: 100,
      messages: [],
      stream: true,
    });

    const seen: unknown[] = [];
    for await (const event of stream) {
      seen.push(event);
      await client.flush();
      expect(captured).toHaveLength(0);
    }

    expect(seen).toHaveLength(3);
    await client.flush();
    expect(captured).toHaveLength(1);
    await client.flush();
    expect(captured[0]).toMatchObject({ input_tokens: 20, output_tokens: 10, status: "success" });
    inst.uninstrument();
  });
});
