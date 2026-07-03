/**
 * costorahNodeMiddleware — generic Node.js http/https integration
 * (EP-18.6).
 *
 *     import http from "node:http";
 *     import { costorahNodeMiddleware } from "@costorah/sdk/node";
 *
 *     const withCostorah = costorahNodeMiddleware();
 *     const server = http.createServer((req, res) => {
 *       withCostorah(req, res, () => {
 *         res.end("ok");
 *       });
 *     });
 *
 * For standalone `http`/`https` servers, background workers, cron jobs,
 * and CLI applications that don't sit behind a framework like Express —
 * anything that hands you a raw `http.IncomingMessage`/
 * `http.ServerResponse` pair. No dependency on any specific framework
 * (this is what `costorahMiddleware()` in `./express.ts` is
 * structurally compatible with, since Express's own `req`/`res` are
 * built on Node's `http` types).
 *
 * Same behavior as every other integration: auto-init from
 * `COSTORAH_API_KEY`, request context capture (request ID, path,
 * method, optional organization ID), an echoed
 * `X-Costorah-Request-Id` response header, graceful degradation with no
 * API key configured.
 */

import { Costorah } from "./client.js";
import { runWithRequestContext } from "./context.js";
import { CostorahError } from "./errors.js";
import { setDefaultClient } from "./instrumentation/submission.js";
import { createConsoleLogger } from "./logging.js";

const _log = createConsoleLogger();

/** Structural subset of `http.IncomingMessage` this middleware needs. */
export interface MinimalIncomingMessage {
  headers: Record<string, string | string[] | undefined>;
  // `| undefined` (not just an optional `?:` property) to match Node's
  // real `http.IncomingMessage`, where `url`/`method` are always
  // present as properties but typed possibly-`undefined` — under
  // `exactOptionalPropertyTypes`, those are different shapes and a
  // real `IncomingMessage` isn't assignable to the narrower `url?:
  // string` form.
  url?: string | undefined;
  method?: string | undefined;
}

/** Structural subset of `http.ServerResponse` this middleware needs. */
export interface MinimalServerResponse {
  setHeader(name: string, value: string): unknown;
}

export interface CostorahNodeMiddlewareOptions {
  apiKey?: string | undefined;
  client?: Costorah;
  organizationId?: string | undefined;
}

/**
 * Returns a handler with the same `(req, res, next)` shape as
 * `costorahMiddleware()` from `./express.ts`, but typed against raw
 * Node `http` request/response objects instead of Express's. `next` is
 * called synchronously (no framework routing to hand control back to)
 * — callers wrap their own request-handling logic inside it.
 */
export function costorahNodeMiddleware(
  options: CostorahNodeMiddlewareOptions = {},
): (req: MinimalIncomingMessage, res: MinimalServerResponse, next: () => void) => void {
  const client = options.client ?? autoInitClient(options.apiKey);
  if (client) setDefaultClient(client);

  return function costorahNodeMiddlewareHandler(
    req: MinimalIncomingMessage,
    res: MinimalServerResponse,
    next: () => void,
  ): void {
    const headerRequestId = req.headers["x-request-id"];
    const requestId =
      (Array.isArray(headerRequestId) ? headerRequestId[0] : headerRequestId) ??
      `req_${generateId()}`;

    const context: Record<string, unknown> = {
      requestId,
      path: req.url ?? "",
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
      "costorah_node_middleware_no_api_key: set COSTORAH_API_KEY, or pass apiKey:/client: to " +
        "costorahNodeMiddleware() — instrumentation will still capture usage locally " +
        "(eventsCaptured) but nothing will be submitted",
    );
    return undefined;
  }

  try {
    const endpoint = process.env.COSTORAH_ENDPOINT ?? "https://api.costorah.com";
    return new Costorah({ apiKey: resolvedKey, endpoint });
  } catch (err) {
    if (err instanceof CostorahError) {
      _log.warn(`costorah_node_middleware_init_failed: ${err.message}`);
      return undefined;
    }
    throw err;
  }
}
