/**
 * costorahLambda — AWS Lambda integration (EP-18.6).
 *
 *     import { costorahLambda } from "@costorah/sdk/lambda";
 *
 *     export const handler = costorahLambda(async (event) => {
 *       return { statusCode: 200, body: JSON.stringify({ ok: true }) };
 *     });
 *
 * With `COSTORAH_API_KEY` set in the environment, this is the entire
 * integration. Recognizes API Gateway REST API (v1) events, API
 * Gateway HTTP API / Lambda Function URL (v2) events, and ALB target
 * group events — for all three, it captures request context (request
 * ID — from an incoming `X-Request-Id` header, or Lambda's own
 * `context.awsRequestId` — route, method, optional organization ID)
 * and, when the handler's return value looks like a proxy-integration
 * response object (`{ statusCode, headers, body }`), echoes the request
 * ID back via an `X-Costorah-Request-Id` response header and captures
 * the response status.
 *
 * EventBridge, SQS, and SNS events (and anything else that isn't one of
 * the HTTP-shaped events above) have no route/method/status to capture
 * — the handler still runs inside ambient request context (using
 * `context.awsRequestId` as the request ID), so any usage event
 * captured inside the handler is still tagged, but no HTTP-specific
 * fields are added.
 *
 * Reuses a single `Costorah` client across warm Lambda invocations — a
 * module-level singleton constructed once (lazily, on first
 * invocation) rather than per-call, which is what makes warm-start
 * reuse actually save the client-construction cost cold starts pay.
 */

import { Costorah } from "./client.js";
import { runWithRequestContext } from "./context.js";
import { CostorahError } from "./errors.js";
import { setDefaultClient } from "./instrumentation/submission.js";
import { createConsoleLogger } from "./logging.js";

const _log = createConsoleLogger();

export interface LambdaContext {
  awsRequestId: string;
}

interface ProxyResponse {
  statusCode?: number;
  headers?: Record<string, string>;
  body?: string;
}

interface ApiGatewayV1Event {
  httpMethod: string;
  path: string;
  headers?: Record<string, string | undefined>;
  requestContext?: { requestId?: string };
}

interface ApiGatewayV2OrLambdaUrlEvent {
  version: "2.0";
  rawPath: string;
  headers?: Record<string, string | undefined>;
  requestContext: { http: { method: string } };
}

interface AlbEvent {
  requestContext: { elb: unknown };
  httpMethod: string;
  path: string;
  headers?: Record<string, string | undefined>;
}

type HttpShapedEvent = ApiGatewayV1Event | ApiGatewayV2OrLambdaUrlEvent | AlbEvent;

function isApiGatewayV2OrLambdaUrl(event: unknown): event is ApiGatewayV2OrLambdaUrlEvent {
  const e = event as Partial<ApiGatewayV2OrLambdaUrlEvent>;
  return e.version === "2.0" && typeof e.requestContext?.http?.method === "string";
}

function isAlb(event: unknown): event is AlbEvent {
  const e = event as Partial<AlbEvent>;
  return typeof e.requestContext === "object" && e.requestContext !== null && "elb" in e.requestContext;
}

function isApiGatewayV1(event: unknown): event is ApiGatewayV1Event {
  const e = event as Partial<ApiGatewayV1Event>;
  return typeof e.httpMethod === "string" && typeof e.path === "string";
}

function isHttpShaped(event: unknown): event is HttpShapedEvent {
  return (
    typeof event === "object" &&
    event !== null &&
    (isApiGatewayV2OrLambdaUrl(event) || isAlb(event) || isApiGatewayV1(event))
  );
}

function httpFields(event: HttpShapedEvent): { method: string; path: string; headers: Record<string, string | undefined> } {
  if (isApiGatewayV2OrLambdaUrl(event)) {
    return { method: event.requestContext.http.method, path: event.rawPath, headers: event.headers ?? {} };
  }
  return { method: event.httpMethod, path: event.path, headers: event.headers ?? {} };
}

function isProxyResponse(value: unknown): value is ProxyResponse {
  return typeof value === "object" && value !== null && "statusCode" in value;
}

export interface CostorahLambdaOptions {
  apiKey?: string | undefined;
  client?: Costorah;
  organizationId?: string | undefined;
}

let cachedClient: Costorah | undefined | null = null; // null = not yet resolved

function resolveWarmClient(options: CostorahLambdaOptions): Costorah | undefined {
  if (options.client) return options.client;
  if (cachedClient !== null) return cachedClient ?? undefined;
  cachedClient = autoInitClient(options.apiKey) ?? undefined;
  return cachedClient;
}

/** Test-only: forces the next invocation to re-resolve the warm client
 * instead of reusing whatever a previous test cached. */
export function resetLambdaClientForTests(): void {
  cachedClient = null;
}

/** Test-only: the client currently cached for warm-invocation reuse
 * (auto-init path only — never populated when a caller passes an
 * explicit `client:` option, since there's nothing to cache in that
 * case). Lets tests assert reuse directly instead of only inferring it
 * from "didn't throw." */
export function getCachedLambdaClientForTests(): Costorah | undefined {
  return cachedClient ?? undefined;
}

export function costorahLambda<TEvent = unknown, TResult = unknown>(
  handler: (event: TEvent, context: LambdaContext) => Promise<TResult> | TResult,
  options: CostorahLambdaOptions = {},
): (event: TEvent, context: LambdaContext) => Promise<TResult> {
  return async function costorahLambdaHandler(event: TEvent, context: LambdaContext): Promise<TResult> {
    const client = resolveWarmClient(options);
    if (client) setDefaultClient(client);

    if (!isHttpShaped(event)) {
      // EventBridge / SQS / SNS / anything else — ambient context only,
      // no HTTP fields.
      return runWithRequestContext({ requestId: context.awsRequestId }, () => handler(event, context));
    }

    const { method, path, headers } = httpFields(event);
    const headerRequestId = headers["x-request-id"] ?? headers["X-Request-Id"];
    const requestId = headerRequestId ?? context.awsRequestId;

    const contextFields: Record<string, unknown> = { requestId, path, method };
    if (options.organizationId) contextFields.organizationId = options.organizationId;

    const result = await runWithRequestContext(contextFields, () => handler(event, context));

    if (isProxyResponse(result)) {
      result.headers = { ...result.headers, "X-Costorah-Request-Id": requestId };
    }
    return result;
  };
}

function autoInitClient(apiKey: string | undefined): Costorah | undefined {
  const resolvedKey = apiKey ?? process.env.COSTORAH_API_KEY;
  if (!resolvedKey) {
    _log.warn(
      "costorah_lambda_no_api_key: set COSTORAH_API_KEY, or pass apiKey:/client: to " +
        "costorahLambda() — instrumentation will still capture usage locally " +
        "(eventsCaptured) but nothing will be submitted",
    );
    return undefined;
  }

  try {
    const endpoint = process.env.COSTORAH_ENDPOINT ?? "https://api.costorah.com";
    return new Costorah({ apiKey: resolvedKey, endpoint });
  } catch (err) {
    if (err instanceof CostorahError) {
      _log.warn(`costorah_lambda_init_failed: ${err.message}`);
      return undefined;
    }
    throw err;
  }
}
