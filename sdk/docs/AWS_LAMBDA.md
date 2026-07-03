# AWS Lambda Guide (EP-18.6)

## Install

```bash
npm install @costorah/sdk
export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
```

## Quick start

```typescript
import { costorahLambda } from "@costorah/sdk/lambda";

export const handler = costorahLambda(async (event) => {
  return { statusCode: 200, body: JSON.stringify({ ok: true }) };
});
```

## Supported event shapes

| Trigger | Detected via | Captures |
|---|---|---|
| API Gateway REST API (v1) | `httpMethod`/`path` fields | route, method, status (via response headers) |
| API Gateway HTTP API / Lambda Function URL (v2) | `version === "2.0"` + `requestContext.http.method` | route, method, status |
| ALB target group | `requestContext.elb` | route, method, status |
| EventBridge, SQS, SNS, anything else | (fallback — no HTTP shape recognized) | ambient context only (`context.awsRequestId` as the request ID) — no route/method/status, since there isn't one |

For the three HTTP-shaped event types, the request ID is read from an
incoming `X-Request-Id` header, falling back to
`context.awsRequestId`, and echoed back via an
`X-Costorah-Request-Id` header on the response — but only when the
handler's return value looks like a proxy-integration response object
(`{ statusCode, headers, body }`); if your handler returns something
else, no header is added (there's no response object to attach it to).

## Context reuse — cold starts vs. warm invocations

A single `Costorah` client is reused across warm invocations — a
module-level singleton, constructed once (lazily, on first invocation)
rather than per-call. This is what makes warm-start reuse actually save
the client-construction cost cold starts pay: the client (and its
background delivery worker) survives for the lifetime of the Lambda
execution environment, not just one invocation.

This only applies when relying on auto-init from `COSTORAH_API_KEY` — if
you pass an explicit `client:` option, that client is used as-is on
every invocation (nothing to cache, since you already control its
lifetime).

## What gets captured

Request ID, route, method, optional organization ID (via
`costorahLambda(handler, { organizationId })`) — attached to
`metadata.requestContext` on every usage event captured during that
invocation.

## Version compatibility

Targets the Node 20.x Lambda runtime (Node 18+ generally works, matching
this SDK's overall `engines.node` floor).

## Troubleshooting

- **No `X-Costorah-Request-Id` on the response** — your handler's return
  value doesn't look like a proxy-integration response object
  (`{ statusCode, ... }`); this is expected for non-proxy integrations
  or custom response shapes.
- **Client re-constructed on every invocation** (no warm-start benefit)
  — confirm you're not passing an explicit `client:` option (which
  always bypasses the cache) and that the Lambda execution environment
  is actually being reused (AWS decides this, not your code — cold vs.
  warm is not fully controllable).
