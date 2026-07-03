import { describe, expect, it } from "vitest";

import { InstrumentationError } from "../../src/instrumentation/base.js";
import { CohereInstrumentor } from "../../src/instrumentation/cohere.js";
import { createTestClient } from "./testUtils.js";

function fakeCohereClient() {
  return {
    chat: async (params: unknown) => ({
      params,
      text: "hi",
      usage: { tokens: { inputTokens: 14, outputTokens: 6 } },
    }),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    chatStream: async (_params: unknown): Promise<any> => {
      async function* gen() {
        yield { type: "content-delta", delta: { message: { content: { text: "h" } } } };
        yield {
          type: "message-end",
          response: { usage: { tokens: { inputTokens: 11, outputTokens: 5 } } },
        };
      }
      return gen();
    },
  };
}

describe("CohereInstrumentor — client-scoped lifecycle", () => {
  it("requires a client instance — zero-arg instrument() throws", () => {
    const inst = new CohereInstrumentor();
    expect(() => inst.instrument()).toThrow(InstrumentationError);
  });

  it("instrument(client)/uninstrument() wrap and restore only the given instance", () => {
    const target = fakeCohereClient();
    const originalChat = target.chat;
    const inst = new CohereInstrumentor();
    inst.instrument(target as never);
    expect(target.chat).not.toBe(originalChat);
    inst.uninstrument();
    expect(target.chat).toBe(originalChat);
  });
});

describe("CohereInstrumentor — capture", () => {
  it("captures usage on a successful chat() call", async () => {
    const target = fakeCohereClient();
    const { client, captured } = createTestClient();
    const inst = new CohereInstrumentor({ client });
    inst.instrument(target as never);

    await target.chat({ model: "command-r-plus", messages: [] });

    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({
      provider: "cohere",
      model: "command-r-plus",
      input_tokens: 14,
      output_tokens: 6,
      status: "success",
    });
    inst.uninstrument();
  });

  it("submits an error event and re-throws on failure", async () => {
    const target = fakeCohereClient();
    target.chat = async () => {
      throw new Error("invalid api key");
    };
    const { client, captured } = createTestClient();
    const inst = new CohereInstrumentor({ client });
    inst.instrument(target as never);

    await expect(target.chat({ model: "command-r-plus", messages: [] })).rejects.toThrow(
      "invalid api key",
    );
    expect(captured[0]).toMatchObject({ status: "error", input_tokens: 0 });
    inst.uninstrument();
  });

  it("streaming: aggregates from the terminal message-end event", async () => {
    const target = fakeCohereClient();
    const { client, captured } = createTestClient();
    const inst = new CohereInstrumentor({ client });
    inst.instrument(target as never);

    const stream = await target.chatStream({ model: "command-r-plus", messages: [] });
    const seen: unknown[] = [];
    for await (const event of stream) {
      seen.push(event);
      expect(captured).toHaveLength(0);
    }

    expect(seen).toHaveLength(2);
    expect(captured).toHaveLength(1);
    expect(captured[0]).toMatchObject({ input_tokens: 11, output_tokens: 5, status: "success" });
    inst.uninstrument();
  });
});
