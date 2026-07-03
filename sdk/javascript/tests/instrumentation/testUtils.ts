import { Costorah } from "../../src/client.js";

/** Raw wire-format (snake_case) usage payload, exactly as posted to
 * POST /v1/ingest/usage — see `client.ts::buildPayload`. */
export type CapturedPayload = Record<string, unknown>;

/** A real `Costorah` client wired to a fake `fetch` that always succeeds
 * immediately and records every posted payload — lets instrumentation
 * tests exercise the real submit()/track()/buildPayload() path without
 * touching the network, and inspect exactly what was captured. */
export function createTestClient(): { client: Costorah; captured: CapturedPayload[] } {
  const captured: CapturedPayload[] = [];
  const client = new Costorah(
    { apiKey: "costorah_live_test" },
    {
      fetchImpl: async (_url, init) => {
        const body = init?.body ? JSON.parse(String(init.body)) : {};
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
