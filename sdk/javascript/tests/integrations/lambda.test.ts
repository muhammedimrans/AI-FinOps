import { beforeEach, describe, expect, it } from "vitest";

import { Costorah } from "../../src/client.js";
import { makeExtractedUsage } from "../../src/instrumentation/base.js";
import { setDefaultClient, submit } from "../../src/instrumentation/submission.js";
import {
  costorahLambda,
  getCachedLambdaClientForTests,
  resetLambdaClientForTests,
} from "../../src/lambda.js";

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
  resetLambdaClientForTests();
});

describe("costorahLambda", () => {
  it("captures request context from an API Gateway v1 (REST API) event", async () => {
    const { client, captured } = createTestClient();
    const handler = costorahLambda(
      async () => {
        await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
        return { statusCode: 200, body: "{}" };
      },
      { client, organizationId: "org_1" },
    );

    const result = await handler(
      {
        httpMethod: "GET",
        path: "/ping",
        headers: { "X-Request-Id": "custom-req-1" },
      },
      { awsRequestId: "aws-req-1" },
    );

    expect(
      (result as unknown as { headers: Record<string, string> }).headers["X-Costorah-Request-Id"],
    ).toBe("custom-req-1");

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({
      requestContext: { requestId: "custom-req-1", path: "/ping", method: "GET", organizationId: "org_1" },
    });
    await client.shutdown();
  });

  it("captures request context from an API Gateway v2 / Lambda Function URL event", async () => {
    const { client, captured } = createTestClient();
    const handler = costorahLambda(
      async () => {
        await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
        return { statusCode: 200, body: "{}" };
      },
      { client },
    );

    await handler(
      {
        version: "2.0",
        rawPath: "/v2ping",
        requestContext: { http: { method: "POST" } },
      },
      { awsRequestId: "aws-req-2" },
    );

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({
      requestContext: { path: "/v2ping", method: "POST" },
    });
    await client.shutdown();
  });

  it("captures request context from an ALB target group event", async () => {
    const { client, captured } = createTestClient();
    const handler = costorahLambda(
      async () => {
        await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
        return { statusCode: 200, body: "{}" };
      },
      { client },
    );

    await handler(
      {
        requestContext: { elb: {} },
        httpMethod: "GET",
        path: "/alb-ping",
      },
      { awsRequestId: "aws-req-3" },
    );

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({ requestContext: { path: "/alb-ping" } });
    await client.shutdown();
  });

  it("falls back to context.awsRequestId when no X-Request-Id header is present", async () => {
    const { client, captured } = createTestClient();
    const handler = costorahLambda(
      async () => {
        await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
        return { statusCode: 200, body: "{}" };
      },
      { client },
    );

    await handler({ httpMethod: "GET", path: "/ping" }, { awsRequestId: "generated-aws-id" });

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({
      requestContext: { requestId: "generated-aws-id" },
    });
    await client.shutdown();
  });

  it("passes non-HTTP events (SQS) through with ambient context but no HTTP fields", async () => {
    const { client, captured } = createTestClient();
    let sawContext: Record<string, unknown> | undefined;
    const handler = costorahLambda(
      async () => {
        const { getRequestContext } = await import("../../src/context.js");
        sawContext = getRequestContext();
        await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
        return { processed: 1 };
      },
      { client },
    );

    const result = await handler(
      { Records: [{ eventSource: "aws:sqs", body: "hello" }] },
      { awsRequestId: "sqs-req-1" },
    );

    expect(result).toEqual({ processed: 1 });
    expect(sawContext).toEqual({ requestId: "sqs-req-1" });

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({ requestContext: { requestId: "sqs-req-1" } });
    expect(captured[0]?.metadata as Record<string, unknown>).not.toHaveProperty(
      "requestContext.path",
    );
    await client.shutdown();
  });

  it("reuses the same auto-initialized client across warm invocations", async () => {
    const originalKey = process.env.COSTORAH_API_KEY;
    process.env.COSTORAH_API_KEY = "costorah_live_warm";
    try {
      const handler = costorahLambda(async () => ({ statusCode: 200, body: "{}" }));
      await handler({ httpMethod: "GET", path: "/1" }, { awsRequestId: "a1" });
      const clientAfterFirstCall = getCachedLambdaClientForTests();
      expect(clientAfterFirstCall).toBeDefined();

      await handler({ httpMethod: "GET", path: "/2" }, { awsRequestId: "a2" });
      // Same object reference — not just "another client that happens
      // to behave the same" — proving the warm-start path skips
      // re-constructing a Costorah client on the second invocation.
      expect(getCachedLambdaClientForTests()).toBe(clientAfterFirstCall);

      await clientAfterFirstCall?.shutdown();
    } finally {
      if (originalKey !== undefined) process.env.COSTORAH_API_KEY = originalKey;
      else delete process.env.COSTORAH_API_KEY;
    }
  });

  it("does not cache a client when an explicit client: option is passed", async () => {
    const { client } = createTestClient();
    const handler = costorahLambda(async () => ({ statusCode: 200, body: "{}" }), { client });
    await handler({ httpMethod: "GET", path: "/1" }, { awsRequestId: "a1" });
    expect(getCachedLambdaClientForTests()).toBeUndefined();
    await client.shutdown();
  });

  it("degrades gracefully without a client or COSTORAH_API_KEY", async () => {
    const originalKey = process.env.COSTORAH_API_KEY;
    delete process.env.COSTORAH_API_KEY;
    try {
      const handler = costorahLambda(async () => ({ statusCode: 200, body: "{}" }));
      const result = await handler({ httpMethod: "GET", path: "/ping" }, { awsRequestId: "a1" });
      expect((result as { statusCode: number }).statusCode).toBe(200);
    } finally {
      if (originalKey !== undefined) process.env.COSTORAH_API_KEY = originalKey;
    }
  });
});
