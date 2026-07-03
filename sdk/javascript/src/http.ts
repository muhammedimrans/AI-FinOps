/**
 * HTTP transport: POSTs to COSTORAH's Usage Ingestion API (EP-16),
 * authenticated via an Organization API Key (EP-15), with bounded
 * exponential-backoff retry for transient failures.
 *
 * Retry is bounded (`config.maxRetries`, default 3) because `track()` is
 * an awaited call in the caller's request path in this phase (EP-18.1) —
 * unbounded, queued, non-blocking retry with offline persistence is
 * EP-18.3 scope (see `sdk/shared/API_CONTRACT.md`).
 */

import type { ResolvedConfig } from "./config.js";
import { AuthenticationError, NetworkError, RateLimitError, ServerError, ValidationError } from "./errors.js";
import { createConsoleLogger, type Logger } from "./logging.js";
import { sleep } from "./util.js";
import { VERSION } from "./version.js";

const INGEST_PATH = "/v1/ingest/usage";

// Matches EP-17's RetryPolicy and the Python SDK exactly, for consistency
// across the whole COSTORAH ecosystem (sdk/shared/API_CONTRACT.md).
const BACKOFF_SECONDS = [1, 2, 4, 8, 16, 30, 60];

function backoffDelaySeconds(attempt: number): number {
  const index = Math.min(attempt - 1, BACKOFF_SECONDS.length - 1);
  return BACKOFF_SECONDS[index]!;
}

async function safeDetail(response: Response): Promise<string> {
  try {
    const body = (await response.clone().json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail.slice(0, 500);
    }
  } catch {
    // fall through
  }
  return `HTTP ${response.status}`;
}

function parseRetryAfter(response: Response): number | undefined {
  const header = response.headers.get("Retry-After");
  if (header === null) return undefined;
  const value = Number(header);
  return Number.isFinite(value) ? value : undefined;
}

export type FetchLike = typeof fetch;

export interface IngestResponseBody {
  success: boolean;
  usage_id: string;
  request_id: string;
  processed_at: string;
  duplicate: boolean;
}

export class HttpTransport {
  private readonly config: ResolvedConfig;
  private readonly fetchImpl: FetchLike;
  private readonly logger: Logger;

  constructor(config: ResolvedConfig, fetchImpl?: FetchLike, logger?: Logger) {
    this.config = config;
    this.fetchImpl = fetchImpl ?? globalThis.fetch;
    this.logger = logger ?? createConsoleLogger();
    if (!this.fetchImpl) {
      throw new NetworkError(
        "No fetch implementation available. Node 18+ provides global fetch; " +
          "on older runtimes, pass a fetch polyfill.",
      );
    }
  }

  async postUsageEvent(payload: Record<string, unknown>): Promise<IngestResponseBody> {
    let attempt = 0;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      attempt += 1;
      let response: Response;
      try {
        response = await this.doFetch(payload);
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        await this.retryOrThrow(new NetworkError(`request failed: ${message}`), attempt);
        continue;
      }

      const outcome = await this.handleResponse(response, attempt);
      if (outcome !== undefined) return outcome;
      // else: handleResponse already awaited the retry backoff.
    }
  }

  private async doFetch(payload: Record<string, unknown>): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.config.timeout * 1000);
    try {
      return await this.fetchImpl(`${this.config.endpoint}${INGEST_PATH}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.config.apiKey}`,
          "Content-Type": "application/json",
          "User-Agent": `costorah-js/${VERSION}`,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  }

  private async handleResponse(
    response: Response,
    attempt: number,
  ): Promise<IngestResponseBody | undefined> {
    if (response.status === 200) {
      return (await response.json()) as IngestResponseBody;
    }
    if (response.status === 401 || response.status === 403) {
      throw new AuthenticationError(await safeDetail(response), response.status);
    }
    if (response.status === 400 || response.status === 404 || response.status === 422) {
      throw new ValidationError(await safeDetail(response), response.status);
    }
    if (response.status === 429) {
      const retryAfter = parseRetryAfter(response);
      await this.retryOrThrow(
        new RateLimitError(await safeDetail(response), 429, retryAfter),
        attempt,
        retryAfter,
      );
      return undefined;
    }
    if (response.status >= 500) {
      await this.retryOrThrow(
        new ServerError(await safeDetail(response), response.status),
        attempt,
      );
      return undefined;
    }
    throw new ServerError(
      `unexpected status ${response.status}: ${await safeDetail(response)}`,
      response.status,
    );
  }

  private async retryOrThrow(
    error: NetworkError | RateLimitError | ServerError,
    attempt: number,
    delayOverrideSeconds?: number,
  ): Promise<void> {
    if (attempt > this.config.maxRetries) {
      throw error;
    }
    const delaySeconds = delayOverrideSeconds ?? backoffDelaySeconds(attempt);
    this.logger.warn(`retrying after ${error.name}`, {
      attempt,
      maxRetries: this.config.maxRetries,
      delaySeconds,
    });
    await sleep(delaySeconds * 1000);
  }
}
