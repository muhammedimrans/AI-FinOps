# Runtime & Framework Compatibility (EP-18.6)

## Runtimes

| Runtime | Status | Minimum version | Verified how |
|---|---|---|---|
| Node.js | Supported | 18+ (20+, 22+ also targeted) | Full test suite runs on Node in CI |
| Bun | Supported | Latest stable (no specific floor enforced) | Built package run directly under Bun 1.3.11 in this EP; see `BUN.md` |
| Deno | Should work, unverified | Latest stable | Code review only — Deno wasn't available to test in this EP's environment; see `DENO.md` |
| Cloudflare Workers | Supported | Current platform, requires `nodejs_compat` flag | Integration tests against a hand-rolled Workers-shaped `fetch` handler; see `CLOUDFLARE_WORKERS.md` |
| AWS Lambda | Supported | Node 20.x runtime | Integration tests covering API Gateway v1/v2, ALB, and non-HTTP (SQS) event shapes; see `AWS_LAMBDA.md` |

## Frameworks

| Framework | Status | Minimum version |
|---|---|---|
| Express | Supported (EP-18.4) | 4.x+ |
| NestJS | Supported (EP-18.6) | 10+, 11+ (peerDependency range `^10.0.0 \|\| ^11.0.0`) |
| Next.js | Supported (EP-18.6) | 14+, 15+ (App Router + Edge Runtime; no hard version floor since the integration has no `next` package dependency) |

Below-floor framework versions are not currently detected/warned about
on the JavaScript side the way `costorah doctor`'s Framework version
compatibility check does for the Python SDK (EP-18.5) — see "What's
different from the Python CLI" below.

## `detectRuntime()` / `detectFrameworks()`

Exported from `@costorah/sdk`'s main entry point:

```typescript
import { detectRuntime, detectRuntimeVersion, detectFrameworks } from "@costorah/sdk";

detectRuntime();        // "node" | "bun" | "deno" | "cloudflare-workers" | "lambda" | "browser" | "unknown"
detectRuntimeVersion();  // e.g. "22.22.2", or undefined where not applicable
await detectFrameworks(); // e.g. ["express", "nestjs"]
```

Runtime detection priority (see `src/runtime.ts`'s docstring for the
full rationale): Bun and Deno are checked before the generic Node
fallback (since both also expose Node-compatible globals), Cloudflare
Workers is checked via its `navigator.userAgent` marker (recommended by
Cloudflare's own docs) independent of `process`-based checks, and Lambda
is detected via the `AWS_LAMBDA_FUNCTION_NAME` env var Node has access
to.

## What's different from the Python CLI

Python's `costorah` package ships a console script (`costorah doctor`)
that runs from a shell and reports SDK/Configuration/Connectivity/
Authentication/Framework/Provider status. **The JavaScript SDK has no
equivalent CLI binary** — `costorah` is a Python-only console script
(declared in `sdk/python/pyproject.toml`'s `[project.scripts]`), and
building a second, separate CLI distribution for JavaScript was out of
scope for this EP. `detectRuntime()`/`detectFrameworks()` above are the
programmatic equivalent, importable directly by application code, but
there is no `npx costorah doctor`-style shell command. This is an
explicit scope decision, not an oversight — see the EP-18.6 final report
for the full accounting of what was and wasn't built.

## Never captured, in any integration

Request bodies, cookies, headers beyond `X-Request-Id`, query strings,
secrets, or API keys. See `SECURITY.md`.
