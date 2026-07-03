# Deno Guide (EP-18.6)

## Compatibility status: verified by code review only

Unlike Bun (see `BUN.md`), **Deno was not installed in the sandbox this
Engineering Package was built in**, so its compatibility could not be
empirically verified the way Bun's was — this is stated plainly rather
than claiming a test pass that didn't happen, consistent with this
project's practice throughout every prior Engineering Package.

What follows is a compatibility assessment based on direct code review
of every module this SDK's core and integrations touch, checked against
Deno's documented Node compatibility:

| API this SDK uses | Deno support |
|---|---|
| Global `fetch` | Native, since Deno 1.0 |
| Global `crypto.randomUUID()` | Native, since Deno 1.0 |
| `node:async_hooks`'s `AsyncLocalStorage` | Supported via Deno's npm/Node compatibility layer (`node:` specifiers), since Deno 1.25+ |
| `process.env` | Supported via Deno's Node compatibility layer, or Deno's own `Deno.env` (this SDK does not use `Deno.env` directly — see below) |
| No `fs`, `child_process`, or other Node-only APIs outside `node:async_hooks` | Confirmed by review — `costorah`'s core and every EP-18.6 integration module import only `node:async_hooks` from Node's built-in module set |

## The one real gap: `process.env`

Every integration in this SDK (Node, Express, Lambda, Next.js) reads
`COSTORAH_API_KEY`/`COSTORAH_ENDPOINT` via `process.env`. Deno supports
`process.env` **only** when run with `--allow-env` and either the
`node:process` compatibility import or (as of recent Deno versions) the
`process` global being available without an explicit import in npm
compatibility mode. Running a Deno script that imports `@costorah/sdk`
via `npm:@costorah/sdk` should have `process.env` available
automatically through Deno's npm compatibility layer; running under
Deno's native `Deno.env`-only mode without npm compatibility would
require setting `process.env.COSTORAH_API_KEY` manually before importing
the SDK, e.g.:

```typescript
// deno run --allow-net --allow-env main.ts
import process from "node:process";
process.env.COSTORAH_API_KEY ??= Deno.env.get("COSTORAH_API_KEY") ?? "";

import { Costorah } from "npm:@costorah/sdk";
```

## What this means in practice

- Import via `npm:@costorah/sdk` (Deno's npm compatibility mode) rather
  than a raw ESM URL import — this SDK is published to npm only, not as
  a Deno-native module.
- `costorahHandler`/`costorahWorker` (both fetch-API-shaped,
  framework-agnostic) are the most natural fit for a Deno HTTP server
  (`Deno.serve`), for the same reason described in `BUN.md`.
- No code changes were made to accommodate Deno specifically in this EP
  — the assessment above is that none should be *necessary*, but this
  has not been proven by running it, only by review. Treat this as
  "should work," not "verified working," until it's actually run.
