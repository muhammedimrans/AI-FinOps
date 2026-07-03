/**
 * Submits an ExtractedUsage event to COSTORAH by reusing the EP-18.1
 * `Costorah` client's `track()` — no separate HTTP/auth/retry logic is
 * implemented here, per the ticket's "Reuse EP-18.1 SDK Core" directive.
 *
 * Telemetry submission must never break the caller's actual AI request:
 * any failure (missing API key, network error, validation error,
 * exhausted retries) is caught and swallowed here, never thrown into the
 * instrumented provider SDK call.
 */

import { Costorah } from "../client.js";
import { CostorahError } from "../errors.js";
import type { TrackParams } from "../types.js";
import type { ExtractedUsage } from "./base.js";

let defaultClient: Costorah | undefined;
let defaultClientFailed = false;

function getOrBuildClient(explicitClient: Costorah | undefined): Costorah | undefined {
  if (explicitClient) return explicitClient;
  if (defaultClient) return defaultClient;
  if (defaultClientFailed) return undefined;

  const apiKey = typeof process !== "undefined" ? process.env?.COSTORAH_API_KEY : undefined;
  if (!apiKey) {
    defaultClientFailed = true;
    return undefined;
  }

  try {
    const endpoint =
      (typeof process !== "undefined" ? process.env?.COSTORAH_ENDPOINT : undefined) ??
      "https://api.costorah.com";
    defaultClient = new Costorah({ apiKey, endpoint });
    return defaultClient;
  } catch {
    defaultClientFailed = true;
    return undefined;
  }
}

/** Best-effort submission. Resolves true if the event was accepted by
 * COSTORAH, false for any failure. Never rejects. */
export async function submit(usage: ExtractedUsage, client?: Costorah): Promise<boolean> {
  const resolved = getOrBuildClient(client);
  if (!resolved) return false;

  try {
    const params: TrackParams = {
      provider: usage.provider,
      model: usage.model,
      inputTokens: usage.inputTokens,
      outputTokens: usage.outputTokens,
      cost: usage.cost,
      currency: usage.currency,
      status: usage.status,
      requestId: usage.requestId,
      timestamp: usage.timestamp,
      metadata: usage.metadata,
    };
    if (usage.cachedTokens !== undefined) params.cachedTokens = usage.cachedTokens;
    if (usage.totalTokens !== undefined) params.totalTokens = usage.totalTokens;
    if (usage.latencyMs !== undefined) params.latencyMs = usage.latencyMs;

    await resolved.track(params);
    return true;
  } catch (err) {
    if (err instanceof CostorahError) return false;
    throw err;
  }
}

/** Test-only helper — clears the lazily-built module-level singleton so
 * each test starts from a clean slate. */
export function resetDefaultClientForTests(): void {
  defaultClient = undefined;
  defaultClientFailed = false;
}
