/**
 * Next.js integration (EP-18.6).
 *
 * App Router Route Handlers, and Next Middleware (both are Web Fetch
 * API `Request` -> `Response` functions — `NextRequest`/`NextResponse`
 * are structural subtypes of the standard `Request`/`Response`, so no
 * dependency on the `next` package is needed at the type level):
 *
 *     import { costorahHandler } from "@costorah/sdk/next";
 *
 *     export const POST = costorahHandler(async (req) => {
 *       return Response.json({ ok: true });
 *     });
 *
 * Works identically under the Node.js runtime and the Edge runtime
 * (`export const runtime = "edge"`) — both expose `Request`/`Response`
 * and `process.env` (Edge exposes env vars configured in the platform
 * dashboard through the same `process.env` interface Node.js code
 * expects), so configuration is read from `COSTORAH_API_KEY`/
 * `COSTORAH_ENDPOINT` exactly like the Node/Express integrations.
 *
 * Pages Router API Routes use a different, older `(req, res)` handler
 * shape (closer to a raw Node `http` handler than to `Request`/
 * `Response`) — use `costorahApiRoute` for those:
 *
 *     import { costorahApiRoute } from "@costorah/sdk/next";
 *
 *     export default costorahApiRoute((req, res) => {
 *       res.status(200).json({ ok: true });
 *     });
 *
 * Server Actions are deliberately not wrapped: a Server Action is a
 * plain async function with no `Request`/`Response` object passed to
 * it at all (Next.js handles the HTTP layer internally before invoking
 * it), so there is no per-invocation object for a wrapper to attach
 * request context to. See `sdk/docs/NEXTJS.md` for the (manual
 * `client.track()`-based) pattern to use instrumentation inside a
 * Server Action instead.
 */

import { Costorah } from "./client.js";
import { runWithRequestContext } from "./context.js";
import { CostorahError } from "./errors.js";
import { setDefaultClient } from "./instrumentation/submission.js";
import { createConsoleLogger } from "./logging.js";
import type { MinimalIncomingMessage, MinimalServerResponse } from "./node.js";

const _log = createConsoleLogger();

export interface CostorahNextOptions {
  apiKey?: string | undefined;
  client?: Costorah;
  organizationId?: string | undefined;
}

function generateId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replace(/-/g, "")
    : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

function autoInitClient(apiKey: string | undefined, integration: string): Costorah | undefined {
  const resolvedKey = apiKey ?? process.env.COSTORAH_API_KEY;
  if (!resolvedKey) {
    _log.warn(
      `costorah_${integration}_no_api_key: set COSTORAH_API_KEY, or pass apiKey:/client: — ` +
        "instrumentation will still capture usage locally (eventsCaptured) but nothing will be submitted",
    );
    return undefined;
  }
  try {
    const endpoint = process.env.COSTORAH_ENDPOINT ?? "https://api.costorah.com";
    return new Costorah({ apiKey: resolvedKey, endpoint });
  } catch (err) {
    if (err instanceof CostorahError) {
      _log.warn(`costorah_${integration}_init_failed: ${err.message}`);
      return undefined;
    }
    throw err;
  }
}

/**
 * Wraps an App Router Route Handler or Next Middleware function
 * (anything shaped `(request: Request, ...rest) => Response |
 * Promise<Response>`). Captures request context (request ID, path,
 * method, optional organization ID) and echoes the request ID back via
 * an `X-Costorah-Request-Id` response header.
 */
export function costorahHandler<TArgs extends unknown[]>(
  handler: (request: Request, ...rest: TArgs) => Promise<Response> | Response,
  options: CostorahNextOptions = {},
): (request: Request, ...rest: TArgs) => Promise<Response> {
  const client = options.client ?? autoInitClient(options.apiKey, "nextjs");
  if (client) setDefaultClient(client);

  return async function costorahHandlerWrapped(request: Request, ...rest: TArgs): Promise<Response> {
    const url = new URL(request.url);
    const requestId = request.headers.get("x-request-id") ?? `req_${generateId()}`;
    const contextFields: Record<string, unknown> = {
      requestId,
      path: url.pathname,
      method: request.method,
    };
    if (options.organizationId) contextFields.organizationId = options.organizationId;

    const response = await runWithRequestContext(contextFields, () => handler(request, ...rest));
    const headers = new Headers(response.headers);
    headers.set("X-Costorah-Request-Id", requestId);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  };
}

/**
 * Wraps a Pages Router API Route handler — the legacy `(req, res) =>
 * void` shape, structurally compatible with `costorahNodeMiddleware`'s
 * request/response types since Next's `NextApiRequest`/
 * `NextApiResponse` extend Node's `http.IncomingMessage`/
 * `http.ServerResponse`.
 */
export function costorahApiRoute<
  Req extends MinimalIncomingMessage = MinimalIncomingMessage,
  Res extends MinimalServerResponse = MinimalServerResponse,
>(
  handler: (req: Req, res: Res) => unknown | Promise<unknown>,
  options: CostorahNextOptions = {},
): (req: Req, res: Res) => Promise<unknown> {
  const client = options.client ?? autoInitClient(options.apiKey, "nextjs_api_route");
  if (client) setDefaultClient(client);

  return async function costorahApiRouteWrapped(req: Req, res: Res): Promise<unknown> {
    const headerRequestId = req.headers["x-request-id"];
    const requestId =
      (Array.isArray(headerRequestId) ? headerRequestId[0] : headerRequestId) ?? `req_${generateId()}`;

    const contextFields: Record<string, unknown> = {
      requestId,
      path: req.url ?? "",
      method: req.method ?? "",
    };
    if (options.organizationId) contextFields.organizationId = options.organizationId;

    res.setHeader("X-Costorah-Request-Id", requestId);
    return runWithRequestContext(contextFields, () => handler(req, res));
  };
}
