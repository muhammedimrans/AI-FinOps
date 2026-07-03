/**
 * costorahMiddleware — Express integration (EP-18.4).
 *
 *     import express from "express";
 *     import { costorahMiddleware } from "@costorah/sdk/express";
 *
 *     const app = express();
 *     app.use(costorahMiddleware());
 *
 * With `COSTORAH_API_KEY` set in the environment, this is the entire
 * integration — no other setup. Per request, it:
 *
 *   - Auto-initializes a `Costorah` client (once, at app startup) from
 *     `COSTORAH_API_KEY`/`COSTORAH_ENDPOINT`, or an explicit `apiKey`/
 *     `client` option, and wires it as the default client every
 *     instrumentor submits through (via
 *     `costorah/instrumentation`'s `setDefaultClient`) — combine with
 *     e.g. `new OpenAIInstrumentor().instrument()` at startup and every
 *     request handled through this app gets automatic usage tracking
 *     with zero per-request code.
 *   - Captures request context (a request ID — the incoming
 *     `X-Request-Id` header if present, otherwise a generated one —
 *     path, and method) and attaches it to every usage event captured
 *     during that request, under `metadata.requestContext`.
 *   - Attaches `organizationId` (if configured) to that same context.
 *   - Echoes the request ID back via an `X-Costorah-Request-Id` response
 *     header, so a caller can correlate their request with the usage
 *     events it produced.
 *
 * Entirely optional: an app that never adds this middleware behaves
 * exactly as it does today; instrumentation and manual `track()` calls
 * work identically with or without it. No dependency on Express's own
 * types (or the `express` package at all) — the request/response
 * parameters below are typed structurally, matching Express's real
 * `Request`/`Response`/`NextFunction` without requiring `@types/express`
 * to be installed.
 */

import { Costorah } from "./client.js";
import { runWithRequestContext } from "./context.js";
import { CostorahError } from "./errors.js";
import { setDefaultClient } from "./instrumentation/submission.js";
import { createConsoleLogger } from "./logging.js";

const _log = createConsoleLogger();

/** Structural subset of Express's `Request` this middleware needs. */
export interface MinimalRequest {
  headers: Record<string, string | string[] | undefined>;
  path?: string;
  method?: string;
  url?: string;
}

/** Structural subset of Express's `Response` this middleware needs. */
export interface MinimalResponse {
  setHeader(name: string, value: string): unknown;
}

export type MinimalNextFunction = (err?: unknown) => void;

export interface CostorahMiddlewareOptions {
  apiKey?: string | undefined;
  client?: Costorah;
  organizationId?: string | undefined;
}

export function costorahMiddleware(
  options: CostorahMiddlewareOptions = {},
): (req: MinimalRequest, res: MinimalResponse, next: MinimalNextFunction) => void {
  const client = options.client ?? autoInitClient(options.apiKey);
  if (client) setDefaultClient(client);

  return function costorahMiddlewareHandler(
    req: MinimalRequest,
    res: MinimalResponse,
    next: MinimalNextFunction,
  ): void {
    const headerRequestId = req.headers["x-request-id"];
    const requestId =
      (Array.isArray(headerRequestId) ? headerRequestId[0] : headerRequestId) ??
      `req_${generateId()}`;

    const context: Record<string, unknown> = {
      requestId,
      path: req.path ?? req.url ?? "",
      method: req.method ?? "",
    };
    if (options.organizationId) context.organizationId = options.organizationId;

    res.setHeader("X-Costorah-Request-Id", requestId);
    runWithRequestContext(context, () => next());
  };
}

function generateId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replace(/-/g, "")
    : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

function autoInitClient(apiKey: string | undefined): Costorah | undefined {
  const resolvedKey = apiKey ?? process.env.COSTORAH_API_KEY;
  if (!resolvedKey) {
    _log.warn(
      "costorah_middleware_no_api_key: set COSTORAH_API_KEY, or pass apiKey:/client: to " +
        "costorahMiddleware() — instrumentation will still capture usage locally " +
        "(eventsCaptured) but nothing will be submitted",
    );
    return undefined;
  }

  try {
    const endpoint = process.env.COSTORAH_ENDPOINT ?? "https://api.costorah.com";
    return new Costorah({ apiKey: resolvedKey, endpoint });
  } catch (err) {
    if (err instanceof CostorahError) {
      _log.warn(`costorah_middleware_init_failed: ${err.message}`);
      return undefined;
    }
    throw err;
  }
}
