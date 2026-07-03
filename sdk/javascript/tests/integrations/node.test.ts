import http, { type IncomingMessage, type Server, type ServerResponse } from "node:http";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { Costorah } from "../../src/client.js";
import { makeExtractedUsage } from "../../src/instrumentation/base.js";
import { setDefaultClient, submit } from "../../src/instrumentation/submission.js";
import { costorahNodeMiddleware } from "../../src/node.js";

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

function listen(
  handler: (req: IncomingMessage, res: ServerResponse) => void,
): Promise<{ server: Server; port: number }> {
  return new Promise((resolve) => {
    const server = http.createServer(handler);
    server.listen(0, () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      resolve({ server, port });
    });
  });
}

const servers: Server[] = [];

afterEach(async () => {
  await Promise.all(servers.splice(0).map((s) => new Promise((r) => s.close(r))));
  setDefaultClient(undefined);
});

beforeEach(() => {
  setDefaultClient(undefined);
});

describe("costorahNodeMiddleware", () => {
  it("sets the default client and captures request context", async () => {
    const { client, captured } = createTestClient();
    const withCostorah = costorahNodeMiddleware({ client, organizationId: "org_1" });

    const { server, port } = await listen((req, res) => {
      withCostorah(req, res, () => {
        void submit(
          makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }),
        ).then(() => {
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ ok: true }));
        });
      });
    });
    servers.push(server);

    const resp = await fetch(`http://localhost:${port}/ping`, {
      headers: { "X-Request-Id": "custom-req-1" },
    });
    expect(resp.status).toBe(200);
    expect(resp.headers.get("x-costorah-request-id")).toBe("custom-req-1");

    await client.flush(5000);
    expect(captured).toHaveLength(1);
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

  it("generates a request id when absent", async () => {
    const { client } = createTestClient();
    const withCostorah = costorahNodeMiddleware({ client });

    const { server, port } = await listen((req, res) => {
      withCostorah(req, res, () => {
        res.end("ok");
      });
    });
    servers.push(server);

    const resp = await fetch(`http://localhost:${port}/ping`);
    expect(resp.headers.get("x-costorah-request-id")).toMatch(/^req_/);
    await client.shutdown();
  });

  it("does not leak request context across concurrent requests", async () => {
    const { client, captured } = createTestClient();
    const withCostorah = costorahNodeMiddleware({ client });

    const { server, port } = await listen((req, res) => {
      withCostorah(req, res, () => {
        const requestId = req.url === "/a" ? "ra" : "rb";
        void submit(
          makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId }),
        ).then(() => res.end("ok"));
      });
    });
    servers.push(server);

    await Promise.all([
      fetch(`http://localhost:${port}/a`, { headers: { "X-Request-Id": "req-a" } }),
      fetch(`http://localhost:${port}/b`, { headers: { "X-Request-Id": "req-b" } }),
    ]);

    await client.flush(5000);
    const paths = captured
      .map((c) => (c.metadata as { requestContext: { path: string } }).requestContext.path)
      .sort();
    expect(paths).toEqual(["/a", "/b"]);
    await client.shutdown();
  });

  it("degrades gracefully without a client or COSTORAH_API_KEY", async () => {
    const originalKey = process.env.COSTORAH_API_KEY;
    delete process.env.COSTORAH_API_KEY;
    try {
      const withCostorah = costorahNodeMiddleware();
      const { server, port } = await listen((req, res) => {
        withCostorah(req, res, () => res.end("ok"));
      });
      servers.push(server);

      const resp = await fetch(`http://localhost:${port}/ping`);
      expect(resp.status).toBe(200);
      expect(resp.headers.get("x-costorah-request-id")).toBeTruthy();
    } finally {
      if (originalKey !== undefined) process.env.COSTORAH_API_KEY = originalKey;
    }
  });
});
