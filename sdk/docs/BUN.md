# Bun Guide (EP-18.6)

## Verified compatibility

`@costorah/sdk`'s core (client, instrumentation, reliability layer) and
the Node/Express-style integrations (`costorahNodeMiddleware`,
`costorahMiddleware`) run **unmodified** under Bun — verified in this
Engineering Package by actually running the built package under a real
Bun runtime (`bun 1.3.11`), not just reasoning about API compatibility:

```
$ bun -e "..." # constructs a Costorah client, wraps a node:http
                # server with costorahNodeMiddleware(), makes a real
                # request through it
runtime: bun 1.3.11
status: 200 header: bun-req-1
```

This confirms the ambient-request-context mechanism (`node:async_hooks`'s
`AsyncLocalStorage`, which Bun implements natively as part of its Node
compatibility layer) works correctly under Bun, end to end.

The SDK's own Vitest test suite was also run under `bun run
node_modules/.bin/vitest` against a subset of test files — the client
and Node-middleware tests pass identically to running under Node. Three
`runtime.test.ts` assertions "fail" when the *test suite itself* runs
under Bun rather than Node — this is expected, not a defect:
`detectRuntime()` correctly reports `"bun"` even when a test stubs
another runtime's marker (e.g. `navigator.userAgent`), because Bun's own
`Bun` global is checked first by design (see `detectRuntime()`'s
docstring in `src/runtime.ts` for the priority rationale). Those
specific assertions assume a Node.js host process, which is true in this
repo's CI (Node) but not when literally executed under Bun.

## No Bun-specific integration needed

Bun's own HTTP server API (`Bun.serve`) is fetch-API-shaped
(`(request: Request) => Response`), which is exactly what
`costorahHandler` (from `@costorah/sdk/next`, despite the name, has no
Next.js dependency — see `NEXTJS.md`) and `costorahWorker` (from
`@costorah/sdk/cloudflare`, similarly no Cloudflare dependency) are
already typed against. Either works as a generic
`Request -> Response` wrapper under `Bun.serve`:

```typescript
import { costorahHandler } from "@costorah/sdk/next";

Bun.serve({
  fetch: costorahHandler(async (req) => new Response("ok")),
});
```

## Version compatibility

Verified against Bun 1.3.11 (latest stable at the time of this EP).
No Bun-specific minimum version is enforced — Bun's Node compatibility
layer has covered `node:async_hooks`/`AsyncLocalStorage` and global
`fetch`/`crypto` since well before 1.0.
