# Cloudflare Workers Guide (EP-18.6)

## Install

```bash
npm install @costorah/sdk
```

## wrangler.toml

```toml
compatibility_flags = ["nodejs_compat"]

[vars]
COSTORAH_API_KEY = "costorah_live_xxxxxxxxx"   # or bind as a secret: wrangler secret put COSTORAH_API_KEY
```

The `nodejs_compat` flag is **required**. Ambient request context (the
mechanism every framework integration in this SDK shares) is backed by
`node:async_hooks`'s `AsyncLocalStorage`, which Cloudflare Workers only
exposes under this flag. Every Workers project created after 2024 has
it on by default; if yours predates that, add it explicitly.

## Quick start

```typescript
import { costorahWorker } from "@costorah/sdk/cloudflare";

export default costorahWorker(async (request, env, ctx) => {
  return new Response("ok");
});
```

## Pages Functions / Durable Objects

Also accepts a full `ExportedHandler`-shaped object — only `fetch` is
wrapped, everything else passes through unmodified:

```typescript
export default costorahWorker({
  fetch: async (request, env, ctx) => new Response("ok"),
  scheduled: async (event, env, ctx) => { /* ... */ },
});
```

## Configuration — env bindings, not process.env

Workers has no `process.env` under its native runtime (only under
`nodejs_compat`, and even then it's not the idiomatic way to configure a
Worker). Unlike every Node-based integration in this SDK, configuration
is read from the `env` bindings object passed into `fetch()` on each
request:

| Binding | Purpose |
|---|---|
| `COSTORAH_API_KEY` | required (unless `apiKey`/`client` passed explicitly) |
| `COSTORAH_ENDPOINT` | optional, defaults to `https://api.costorah.com` |

Override the binding names via `costorahWorker(handler, { apiKeyBinding: "MY_KEY", endpointBinding: "MY_ENDPOINT" })`.

## Client reuse across requests in the same isolate

Since bindings are only available once a request arrives, client
construction is deferred to the first `fetch()` call rather than
happening at module-evaluation time — and then cached for the isolate's
lifetime, so subsequent requests in the same isolate reuse it instead of
reconstructing a `Costorah` client every time (analogous to Lambda's
warm-start reuse).

## What gets captured

Request ID (`X-Request-Id` header, or generated), path, method, optional
organization ID — attached to `metadata.requestContext`, echoed back via
an `X-Costorah-Request-Id` response header.

## Version compatibility

Targets the current Workers runtime (`nodejs_compat` flag on). No
separate version pinning applies — Cloudflare rolls the runtime forward
continuously rather than shipping discrete numbered releases the way
Node/Bun/Deno do.

## Troubleshooting

- **`ReferenceError: AsyncLocalStorage is not defined`** (or similar) —
  the `nodejs_compat` compatibility flag is missing from
  `wrangler.toml`.
- **`costorah_worker_no_api_key` warning at every request** — the
  binding name doesn't match; confirm it's set in `wrangler.toml`'s
  `[vars]` or via `wrangler secret put`, and that the binding name
  matches `apiKeyBinding` (default `COSTORAH_API_KEY`).
