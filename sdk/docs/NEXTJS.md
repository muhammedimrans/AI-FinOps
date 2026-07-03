# Next.js Guide (EP-18.6)

## Install

```bash
npm install @costorah/sdk
export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
```

## App Router Route Handlers

```typescript
import { costorahHandler } from "@costorah/sdk/next";

export const POST = costorahHandler(async (req) => {
  return Response.json({ ok: true });
});
```

Works for any HTTP method export (`GET`/`POST`/`PUT`/...) and passes
through extra arguments (e.g. dynamic route `{ params }`) unmodified:

```typescript
export const GET = costorahHandler(async (req, { params }) => {
  return Response.json({ id: params.id });
});
```

## Next Middleware

Same `costorahHandler` — Next Middleware functions are also
`(request: Request) => Response`-shaped (`NextRequest`/`NextResponse`
are structural subtypes of the standard `Request`/`Response`):

```typescript
// middleware.ts
import { costorahHandler } from "@costorah/sdk/next";

export default costorahHandler(async (req) => {
  return NextResponse.next();
});
```

## Edge Runtime

Works unmodified under `export const runtime = "edge"` — the Edge
runtime exposes `Request`/`Response` and `process.env` (for env vars
configured in the platform dashboard), which is all this integration
needs.

## Pages Router API Routes

The legacy `(req, res)` handler shape uses a separate wrapper,
`costorahApiRoute`, since it's structurally different from
`Request`/`Response`:

```typescript
import { costorahApiRoute } from "@costorah/sdk/next";

export default costorahApiRoute((req, res) => {
  res.status(200).json({ ok: true });
});
```

## Server Actions

**Not automatically wrapped.** A Server Action is a plain async
function — Next.js handles the HTTP layer internally before invoking
it, so there is no `Request`/`Response` object passed to a Server
Action for a wrapper to attach request context to. Use manual
`client.track()` (or rely on automatic instrumentation, which doesn't
need request context to function — it only enriches events with it when
available) inside a Server Action instead:

```typescript
"use server";
import { Costorah } from "@costorah/sdk";

const client = new Costorah({ apiKey: process.env.COSTORAH_API_KEY! });

export async function summarize(text: string) {
  // ... call an instrumented provider SDK here; usage is captured
  // automatically by the instrumentor, just without ambient request
  // context (no route/method to attach, since there's no Request object)
}
```

## What gets captured

Request ID (`X-Request-Id` header, or generated), path, method, optional
organization ID — attached to `metadata.requestContext` on every usage
event captured during that request/middleware invocation, echoed back
via an `X-Costorah-Request-Id` response header.

## Version compatibility

Targets Next.js 14+ and 15+. Since `costorahHandler`/`costorahApiRoute`
have no dependency on the `next` package itself (they're typed against
the standard `Request`/`Response` and a structural Node request/response
subset respectively), there's no meaningful lower bound tied to Next's
own version beyond "App Router exists" (Next 13+).

## Troubleshooting

- **No `X-Costorah-Request-Id` header on an Edge Middleware response** —
  confirm the middleware file's default export is the wrapped handler,
  not the raw one.
- **Usage inside a Server Action isn't tagged with request context** —
  expected; see "Server Actions" above.
