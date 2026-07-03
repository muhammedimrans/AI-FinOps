import { gunzipSync } from "node:zlib";

import { Costorah } from "../../src/client.js";

/** Raw wire-format (snake_case) usage payload, exactly as posted to
 * POST /v1/ingest/usage — see `client.ts::buildPayload`. */
export type CapturedPayload = Record<string, unknown>;

/** Decodes a fetch RequestInit body into a UTF-8 string, transparently
 * gunzipping it first if it's gzip-compressed (EP-18.3's reliability
 * layer sends the body as a `Uint8Array`, gzip-compressed above its size
 * threshold — see `reliability/connectionPool.ts`/`compression.ts` —
 * rather than the plain JSON string EP-18.1/EP-18.2 sent). */
function decodeBody(body: unknown): string {
  if (body === undefined || body === null) return "{}";
  if (typeof body === "string") return body;
  const bytes =
    body instanceof Uint8Array
      ? body
      : new TextEncoder().encode(String(body));
  const isGzip = bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
  const decompressed = isGzip ? gunzipSync(bytes) : bytes;
  return new TextDecoder().decode(decompressed);
}

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
        const body = JSON.parse(decodeBody(init?.body));
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
