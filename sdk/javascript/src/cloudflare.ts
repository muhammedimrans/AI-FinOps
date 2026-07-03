/**
 * costorahWorker — Cloudflare Workers integration (EP-18.6).
 *
 *     export default costorahWorker(async (request, env, ctx) => {
 *       return new Response("ok");
 *     });
 *
 * Also accepts a full `ExportedHandler`-shaped object (only `fetch` is
 * wrapped; `scheduled`/`queue`/etc. pass through unmodified) — useful
 * for Pages Functions and Durable Objects, which export the same
 * `{ fetch, ... }` shape:
 *
 *     export default costorahWorker({
 *       fetch: async (request, env, ctx) => new Response("ok"),
 *       scheduled: async (event, env, ctx) => { ... },
 *     });
 *
 * Workers has no `process.env` under its native runtime (only under the
 * `nodejs_compat` compatibility flag), so — unlike every Node-based
 * integration in this SDK — configuration is read from the Workers
 * `env` bindings object passed into `fetch()` on each request, not from
 * `process.env`. Bindings are only available once a request arrives, so
 * client construction is deferred to the first `fetch()` call rather
 * than happening at module-evaluation time (also correct for the
 * "reuse across the same isolate's subsequent requests" case Workers
 * cares about, analogous to Lambda warm starts).
 *
 * No Node.js-specific dependency in this module itself. The one
 * exception, inherited from `costorah/context`, is that ambient request
 * context is backed by `node:async_hooks`'s `AsyncLocalStorage` — which
 * Cloudflare Workers *does* support, but only with the `nodejs_compat`
 * compatibility flag enabled (`compatibility_flags = ["nodejs_compat"]`
 * in `wrangler.toml`). This is documented in
 * `sdk/docs/CLOUDFLARE_WORKERS.md` rather than worked around, since
 * every Workers deployment created after 2024 has this flag on by
 * default.
 */

import { Costorah } from "./client.js";
import { runWithRequestContext } from "./context.js";
import { ConfigurationError, CostorahError } from "./errors.js";
import { setDefaultClient } from "./instrumentation/submission.js";
import { createConsoleLogger } from "./logging.js";

const _log = createConsoleLogger();

export type WorkerFetchHandler<Env = unknown> = (
  request: Request,
  env: Env,
  ctx: unknown,
) => Promise<Response> | Response;

export interface ExportedHandlerLike<Env = unknown> {
  fetch?: WorkerFetchHandler<Env>;
  [key: string]: unknown;
}

export interface CostorahWorkerOptions {
  apiKey?: string | undefined;
  client?: Costorah;
  organizationId?: string | undefined;
  endpoint?: string;
  /** The `env` binding name to read the API key from when `apiKey`/
   * `client` aren't passed explicitly. Defaults to `"COSTORAH_API_KEY"`. */
  apiKeyBinding?: string;
  /** The `env` binding name to read the endpoint override from.
   * Defaults to `"COSTORAH_ENDPOINT"`. */
  endpointBinding?: string;
}

let cachedClient: Costorah | undefined | null = null; // null = not yet resolved

/** Test-only: forces the next invocation to re-resolve the cached
 * client instead of reusing whatever a previous test/isolate cached. */
export function resetWorkerClientForTests(): void {
  cachedClient = null;
}

/** Test-only: the client currently cached for reuse across requests in
 * the same isolate (env-binding auto-init path only — never populated
 * when a caller passes an explicit `client:` option). */
export function getCachedWorkerClientForTests(): Costorah | undefined {
  return cachedClient ?? undefined;
}

function resolveClient(options: CostorahWorkerOptions, env: unknown): Costorah | undefined {
  if (options.client) return options.client;
  if (cachedClient !== null) return cachedClient ?? undefined;

  const envRecord = (env ?? {}) as Record<string, string | undefined>;
  const apiKey = options.apiKey ?? envRecord[options.apiKeyBinding ?? "COSTORAH_API_KEY"];
  const endpoint =
    options.endpoint ?? envRecord[options.endpointBinding ?? "COSTORAH_ENDPOINT"] ?? "https://api.costorah.com";

  if (!apiKey) {
    _log.warn(
      "costorah_worker_no_api_key: bind COSTORAH_API_KEY as a Worker secret/variable, or pass " +
        "apiKey:/client: to costorahWorker() — instrumentation will still capture usage locally " +
        "(eventsCaptured) but nothing will be submitted",
    );
    cachedClient = undefined;
    return undefined;
  }

  try {
    cachedClient = new Costorah({ apiKey, endpoint });
  } catch (err) {
    if (err instanceof CostorahError) {
      _log.warn(`costorah_worker_init_failed: ${err.message}`);
      cachedClient = undefined;
    } else {
      throw err;
    }
  }
  return cachedClient ?? undefined;
}

function generateId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID().replace(/-/g, "")
    : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

export function costorahWorker<Env = unknown>(
  handler: WorkerFetchHandler<Env> | ExportedHandlerLike<Env>,
  options: CostorahWorkerOptions = {},
): ExportedHandlerLike<Env> {
  const fetchHandler = typeof handler === "function" ? handler : handler.fetch;
  if (!fetchHandler) {
    throw new ConfigurationError(
      "costorahWorker() requires either a fetch handler function, or an object with a fetch method",
    );
  }

  const wrappedFetch: WorkerFetchHandler<Env> = async (request, env, ctx) => {
    const client = resolveClient(options, env);
    if (client) setDefaultClient(client);

    const url = new URL(request.url);
    const requestId = request.headers.get("x-request-id") ?? `req_${generateId()}`;
    const contextFields: Record<string, unknown> = {
      requestId,
      path: url.pathname,
      method: request.method,
    };
    if (options.organizationId) contextFields.organizationId = options.organizationId;

    const response = await runWithRequestContext(contextFields, () => fetchHandler(request, env, ctx));

    const headers = new Headers(response.headers);
    headers.set("X-Costorah-Request-Id", requestId);
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  };

  if (typeof handler === "function") return { fetch: wrappedFetch };
  return { ...handler, fetch: wrappedFetch };
}
