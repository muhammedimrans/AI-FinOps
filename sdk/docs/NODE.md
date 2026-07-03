# Generic Node.js Guide (EP-18.6)

For standalone `http`/`https` servers, background workers, cron jobs,
and CLI applications that don't sit behind a framework like Express —
anything that hands you a raw `http.IncomingMessage`/
`http.ServerResponse` pair, or nothing at all.

## Install

```bash
npm install @costorah/sdk
export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
```

## Standalone http/https servers

```typescript
import http from "node:http";
import { costorahNodeMiddleware } from "@costorah/sdk/node";

const withCostorah = costorahNodeMiddleware();
const server = http.createServer((req, res) => {
  withCostorah(req, res, () => {
    res.end("ok");
  });
});
```

No dependency on Express — structurally typed against Node's own
`http.IncomingMessage`/`http.ServerResponse`, the same technique
`costorahMiddleware()` (Express) uses. This is also what
`costorahMiddleware()` and NestJS's `CostorahMiddleware` delegate to
internally.

## Workers, cron jobs, CLI applications

These have no per-request HTTP boundary at all — there's nothing for a
middleware to wrap. Automatic instrumentation (`OpenAIInstrumentor`,
etc.) works identically with or without a framework integration; it's
the ambient *request context* (route/method/request ID tagging) that
needs an HTTP boundary to attach to. For a cron job or worker, either:

- Skip request context entirely — instrumented calls are still captured
  and submitted, just without `metadata.requestContext`.
- Wrap a logical unit of work in `runWithRequestContext` directly:

  ```typescript
  import { runWithRequestContext } from "@costorah/sdk";

  await runWithRequestContext({ requestId: `job_${Date.now()}` }, async () => {
    // any instrumented provider calls in here inherit this context
  });
  ```

## What gets captured

Request ID (`X-Request-Id` header, or generated), path (`req.url`),
method, optional organization ID — attached to
`metadata.requestContext`, echoed back via an `X-Costorah-Request-Id`
response header.

## Version compatibility

Targets Node 18+, 20+, 22+ (matches `package.json`'s `engines.node`
floor of `>=18`).
