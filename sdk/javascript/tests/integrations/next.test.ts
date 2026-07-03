import { beforeEach, describe, expect, it } from "vitest";

import { Costorah } from "../../src/client.js";
import { makeExtractedUsage } from "../../src/instrumentation/base.js";
import { setDefaultClient, submit } from "../../src/instrumentation/submission.js";
import type { MinimalIncomingMessage } from "../../src/node.js";
import { costorahApiRoute, costorahHandler } from "../../src/next.js";

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
});

describe("costorahHandler (App Router / Middleware)", () => {
  it("captures request context and echoes the request id", async () => {
    const { client, captured } = createTestClient();
    const POST = costorahHandler(
      async (req: Request) => {
        expect(req.method).toBe("POST");
        await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
        return Response.json({ ok: true });
      },
      { client, organizationId: "org_1" },
    );

    const request = new Request("https://example.com/api/chat", {
      method: "POST",
      headers: { "X-Request-Id": "custom-req-1" },
    });
    const response = await POST(request);

    expect(response.status).toBe(200);
    expect(response.headers.get("x-costorah-request-id")).toBe("custom-req-1");

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({
      requestContext: {
        requestId: "custom-req-1",
        path: "/api/chat",
        method: "POST",
        organizationId: "org_1",
      },
    });
    await client.shutdown();
  });

  it("generates a request id when absent", async () => {
    const { client } = createTestClient();
    const GET = costorahHandler(async () => new Response("ok"), { client });
    const response = await GET(new Request("https://example.com/ping"));
    expect(response.headers.get("x-costorah-request-id")).toMatch(/^req_/);
    await client.shutdown();
  });

  it("passes extra route-context args through to the handler (dynamic route params)", async () => {
    const { client } = createTestClient();
    let receivedParams: unknown;
    const GET = costorahHandler(
      async (_req: Request, ctx: { params: { id: string } }) => {
        receivedParams = ctx.params;
        return new Response("ok");
      },
      { client },
    );

    await GET(new Request("https://example.com/items/42"), { params: { id: "42" } });
    expect(receivedParams).toEqual({ id: "42" });
    await client.shutdown();
  });

  it("degrades gracefully without a client or COSTORAH_API_KEY", async () => {
    const originalKey = process.env.COSTORAH_API_KEY;
    delete process.env.COSTORAH_API_KEY;
    try {
      const GET = costorahHandler(async () => new Response("ok"));
      const response = await GET(new Request("https://example.com/ping"));
      expect(response.status).toBe(200);
    } finally {
      if (originalKey !== undefined) process.env.COSTORAH_API_KEY = originalKey;
    }
  });
});

interface ResWithEnd {
  setHeader(name: string, value: string): unknown;
  end(body: string): void;
}

describe("costorahApiRoute (Pages Router)", () => {
  it("captures request context and sets the response header", async () => {
    const { client, captured } = createTestClient();
    const handler = costorahApiRoute<MinimalIncomingMessage, ResWithEnd>(
      async (req, res) => {
        await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
        res.end("{}");
      },
      { client },
    );

    const headers: Record<string, string> = {};
    const req = { headers: { "x-request-id": "api-req-1" }, url: "/api/legacy", method: "GET" };
    const res: ResWithEnd = {
      setHeader: (name: string, value: string) => {
        headers[name] = value;
      },
      end: () => undefined,
    };

    await handler(req, res);
    expect(headers["X-Costorah-Request-Id"]).toBe("api-req-1");

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({
      requestContext: { requestId: "api-req-1", path: "/api/legacy", method: "GET" },
    });
    await client.shutdown();
  });
});
