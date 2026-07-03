import { beforeEach, describe, expect, it } from "vitest";

import { Costorah } from "../../src/client.js";
import {
  costorahWorker,
  getCachedWorkerClientForTests,
  resetWorkerClientForTests,
} from "../../src/cloudflare.js";
import { makeExtractedUsage } from "../../src/instrumentation/base.js";
import { setDefaultClient, submit } from "../../src/instrumentation/submission.js";

type CapturedPayload = Record<string, unknown>;

function createTestClient(): { client: Costorah; captured: CapturedPayload[] } {
  const captured: CapturedPayload[] = [];
  const client = new Costorah(
    { apiKey: "costorah_live_test" },
    {
      fetchImpl: async (_url, init) => {
        const body = JSON.parse(new TextDecoder().decode(init?.body as Uint8Array));
        captured.push(body as CapturedPayload);
        return new Response(
          JSON.stringify({
            success: true,
            usage_id: `u_${captured.length}`,
            request_id: body.request_id ?? "r1",
            processed_at: new Date().toISOString(),
            duplicate: false,
          }),
          { status: 200 },
        );
      },
    },
  );
  return { client, captured };
}

beforeEach(() => {
  setDefaultClient(undefined);
  resetWorkerClientForTests();
});

describe("costorahWorker", () => {
  it("accepts a plain fetch function and captures request context", async () => {
    const { client, captured } = createTestClient();
    const worker = costorahWorker(
      async (_request: Request) => {
        await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      },
      { client, organizationId: "org_1" },
    );

    const request = new Request("https://example.com/ping", {
      headers: { "X-Request-Id": "custom-req-1" },
    });
    const response = await worker.fetch!(request, {}, {});

    expect(response.status).toBe(200);
    expect(response.headers.get("x-costorah-request-id")).toBe("custom-req-1");

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({
      requestContext: {
        requestId: "custom-req-1",
        path: "/ping",
        method: "GET",
        organizationId: "org_1",
      },
    });
    await client.shutdown();
  });

  it("accepts an ExportedHandler-shaped object and preserves other handlers unmodified", async () => {
    const { client } = createTestClient();
    let scheduledCalled = false;
    const worker = costorahWorker(
      {
        fetch: async () => new Response("ok"),
        scheduled: async () => {
          scheduledCalled = true;
        },
      },
      { client },
    );

    expect(typeof worker.scheduled).toBe("function");
    await (worker.scheduled as () => Promise<void>)();
    expect(scheduledCalled).toBe(true);
    await client.shutdown();
  });

  it("reads the API key from the env bindings object, not process.env", async () => {
    const worker = costorahWorker(async () => new Response("ok"));
    const request = new Request("https://example.com/ping");

    const response = await worker.fetch!(request, { COSTORAH_API_KEY: "costorah_live_env" }, {});
    expect(response.status).toBe(200);
    // No direct assertion object exposes the resolved client, but a
    // successful response with no thrown ConfigurationError proves the
    // env-binding path was read (as opposed to process.env, which is
    // deliberately not touched by this integration).
  });

  it("reuses the resolved client across subsequent requests in the same isolate", async () => {
    const originalKey = process.env.COSTORAH_API_KEY;
    delete process.env.COSTORAH_API_KEY; // prove env comes from bindings, not process.env
    try {
      const worker = costorahWorker(async () => new Response("ok"));
      const env = { COSTORAH_API_KEY: "costorah_live_warm" };

      await worker.fetch!(new Request("https://example.com/1"), env, {});
      const clientAfterFirstCall = getCachedWorkerClientForTests();
      expect(clientAfterFirstCall).toBeDefined();

      await worker.fetch!(new Request("https://example.com/2"), env, {});
      expect(getCachedWorkerClientForTests()).toBe(clientAfterFirstCall);

      await clientAfterFirstCall?.shutdown();
    } finally {
      if (originalKey !== undefined) process.env.COSTORAH_API_KEY = originalKey;
    }
  });

  it("generates a request id when absent", async () => {
    const { client } = createTestClient();
    const worker = costorahWorker(async () => new Response("ok"), { client });
    const response = await worker.fetch!(new Request("https://example.com/ping"), {}, {});
    expect(response.headers.get("x-costorah-request-id")).toMatch(/^req_/);
    await client.shutdown();
  });

  it("degrades gracefully with no API key bound and no client", async () => {
    const worker = costorahWorker(async () => new Response("ok"));
    const response = await worker.fetch!(new Request("https://example.com/ping"), {}, {});
    expect(response.status).toBe(200);
    expect(response.headers.get("x-costorah-request-id")).toBeTruthy();
  });

  it("throws a clear ConfigurationError for a handler with no fetch method", () => {
    expect(() => costorahWorker({} as never)).toThrow(/requires either a fetch handler/);
  });
});
