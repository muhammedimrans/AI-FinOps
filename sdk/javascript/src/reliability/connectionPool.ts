/**
 * ConnectionPool — reuses HTTP connections across delivery attempts
 * instead of opening a new one per request.
 *
 * Node's global `fetch` (and every `FetchLike` implementation this SDK
 * accepts) is backed by undici, which already keep-alives and pools
 * connections per origin automatically — there is no separate "open a
 * pool" step the way `httpx.AsyncClient` needs in Python. This class's
 * job is just to make sure the whole reliability layer issues every
 * request through the *same* fetch implementation/instance (so whatever
 * pooling the runtime does is actually shared), plus track basic stats.
 */

import type { FetchLike } from "../http.js";
import type { ResolvedConfig } from "../config.js";
import { VERSION } from "../version.js";

export class ConnectionPool {
  private readonly config: ResolvedConfig;
  private readonly fetchImpl: FetchLike;
  requestsSent = 0;

  constructor(config: ResolvedConfig, fetchImpl?: FetchLike) {
    this.config = config;
    this.fetchImpl = fetchImpl ?? globalThis.fetch;
  }

  async post(
    path: string,
    body: Uint8Array,
    headers: Record<string, string>,
  ): Promise<Response> {
    this.requestsSent += 1;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.config.timeout * 1000);
    try {
      return await this.fetchImpl(`${this.config.endpoint}${path}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.config.apiKey}`,
          "User-Agent": `costorah-js/${VERSION}`,
          ...headers,
        },
        body: body as unknown as BodyInit,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  }
}
