import "reflect-metadata";

import { Controller, Get, Inject, Injectable } from "@nestjs/common";
import { Test } from "@nestjs/testing";
import type { INestApplication } from "@nestjs/common";
import request from "supertest";
import { afterEach, describe, expect, it } from "vitest";

import { Costorah } from "../../src/client.js";
import { getRequestContext } from "../../src/context.js";
import { makeExtractedUsage } from "../../src/instrumentation/base.js";
import { setDefaultClient, submit } from "../../src/instrumentation/submission.js";
import { COSTORAH_CLIENT, CostorahMiddleware, CostorahModule, InjectCostorah } from "../../src/nest/index.js";

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

@Injectable()
class PingService {
  async ping(): Promise<{ ok: boolean; contextSeen: Record<string, unknown> | undefined }> {
    // Deliberately awaits, to prove AsyncLocalStorage context survives
    // an async hop between the interceptor's synchronous call and the
    // controller's own async work — the exact concern with wrapping
    // next.handle() (an Observable) in runWithRequestContext.
    await new Promise((resolve) => setTimeout(resolve, 1));
    await submit(makeExtractedUsage({ provider: "openai", model: "gpt-4o", requestId: "r1" }));
    return { ok: true, contextSeen: getRequestContext() };
  }
}

@Controller()
class PingController {
  // Explicit @Inject(token) rather than implicit type-based DI: Vitest
  // transforms TS via esbuild, which doesn't emit the
  // `design:paramtypes` reflect-metadata Nest's implicit constructor
  // injection relies on (only tsc/SWC do) — an explicit token sidesteps
  // that entirely, and is what this SDK's own CostorahMiddleware/
  // CostorahInterceptor already use for the same reason.
  constructor(@Inject(PingService) private readonly pingService: PingService) {}

  @Get("ping")
  async ping() {
    return this.pingService.ping();
  }
}

let app: INestApplication;

afterEach(async () => {
  setDefaultClient(undefined);
  if (app) await app.close();
});

describe("CostorahModule (interceptor path, forRoot default)", () => {
  it("captures request context through an async controller/service chain", async () => {
    const { client, captured } = createTestClient();

    const moduleRef = await Test.createTestingModule({
      imports: [CostorahModule.forRoot({ client, organizationId: "org_1" })],
      controllers: [PingController],
      providers: [PingService],
    }).compile();

    app = moduleRef.createNestApplication();
    await app.init();

    const response = await request(app.getHttpServer())
      .get("/ping")
      .set("X-Request-Id", "custom-req-1")
      .expect(200);

    expect(response.headers["x-costorah-request-id"]).toBe("custom-req-1");
    expect(response.body.contextSeen).toMatchObject({
      requestId: "custom-req-1",
      path: "/ping",
      method: "GET",
      organizationId: "org_1",
    });

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({
      requestContext: { requestId: "custom-req-1", path: "/ping", method: "GET", organizationId: "org_1" },
    });
    await client.shutdown();
  });

  it("provides the Costorah client via DI (@InjectCostorah)", async () => {
    const { client } = createTestClient();

    @Injectable()
    class ClientHolder {
      constructor(@InjectCostorah() public readonly costorah: Costorah) {}
    }

    const moduleRef = await Test.createTestingModule({
      imports: [CostorahModule.forRoot({ client })],
      providers: [ClientHolder],
    }).compile();

    const holder = moduleRef.get(ClientHolder);
    expect(holder.costorah).toBe(client);
    expect(moduleRef.get(COSTORAH_CLIENT)).toBe(client);

    await client.shutdown();
  });
});

describe("CostorahMiddleware (opt-out of the auto interceptor)", () => {
  it("captures request context via middleware instead of the interceptor", async () => {
    const { client, captured } = createTestClient();

    const moduleRef = await Test.createTestingModule({
      imports: [CostorahModule.forRoot({ client, organizationId: "org_mw", autoInterceptor: false })],
      controllers: [PingController],
      providers: [PingService, CostorahMiddleware],
    }).compile();

    app = moduleRef.createNestApplication();
    // Applied directly via app.use (rather than a NestModule's
    // configure()/MiddlewareConsumer, which needs its own module class
    // wiring) — proves CostorahMiddleware works standalone, pulling its
    // options from the same DI-provided COSTORAH_MODULE_OPTIONS
    // CostorahModule.forRoot() registered above.
    const middleware = app.get(CostorahMiddleware);
    app.use(middleware.use.bind(middleware));
    await app.init();

    const response = await request(app.getHttpServer()).get("/ping").expect(200);
    expect(response.headers["x-costorah-request-id"]).toBeTruthy();

    await client.flush(5000);
    expect(captured[0]?.metadata).toMatchObject({
      requestContext: { organizationId: "org_mw" },
    });
    await client.shutdown();
  });
});

describe("CostorahModule degrades gracefully", () => {
  it("without a client or COSTORAH_API_KEY, requests still succeed", async () => {
    const originalKey = process.env.COSTORAH_API_KEY;
    delete process.env.COSTORAH_API_KEY;
    try {
      const moduleRef = await Test.createTestingModule({
        imports: [CostorahModule.forRoot()],
        controllers: [PingController],
        providers: [PingService],
      }).compile();

      app = moduleRef.createNestApplication();
      await app.init();

      await request(app.getHttpServer()).get("/ping").expect(200);
    } finally {
      if (originalKey !== undefined) process.env.COSTORAH_API_KEY = originalKey;
    }
  });
});
