# Framework Integrations (EP-18.4)

## Built in this Engineering Package

Two integrations were built to full, tested depth — one per language,
matching the exact examples in EP-18.4's Success Criteria.

### Python: FastAPI / Starlette

```python
from fastapi import FastAPI
from costorah.integrations.fastapi import CostorahMiddleware

app = FastAPI()
app.add_middleware(CostorahMiddleware)
```

With `COSTORAH_API_KEY` set in the environment, this is the entire
integration. Per request it:

- Auto-initializes a `Costorah` client once, at app startup, from
  `COSTORAH_API_KEY` / `COSTORAH_ENDPOINT` (or explicit `api_key=`/
  `client=` arguments), and wires it as the default client every
  `costorah.instrumentation.*` instrumentor submits through — combine
  with `OpenAIInstrumentor().instrument()` (etc.) at startup and every
  request gets automatic usage tracking with zero per-request code.
- Captures request context — request ID (from the incoming
  `X-Request-Id` header, or generated), path, HTTP method, and an
  optional `organization_id` — and attaches it to every usage event
  captured during that request under `metadata["request_context"]`.
- Echoes the request ID back via an `X-Costorah-Request-Id` response
  header for client-side correlation.
- Degrades gracefully with no API key configured: a warning is logged
  once, instrumentation still runs locally, nothing is submitted.

Requires `fastapi` (or bare `starlette`) to be installed; **not** a
runtime dependency of the `costorah` package itself — importing
`costorah.integrations.fastapi` without FastAPI installed raises a clear
`ImportError` explaining what to `pip install`.

Source: `sdk/python/costorah/integrations/fastapi.py`. Tests:
`sdk/python/tests/integrations/test_fastapi_middleware.py` (9 tests —
default-client wiring, request-context capture, generated-ID fallback,
no-cross-request-leak under concurrency, graceful degradation, env-var
auto-init).

### JavaScript: Express

```typescript
import express from "express";
import { costorahMiddleware } from "@costorah/sdk/express";

const app = express();
app.use(costorahMiddleware());
```

Behaviorally identical to the FastAPI integration above (auto-init,
ambient request context via `AsyncLocalStorage`, response header,
graceful degradation), adapted to Express's middleware signature.
`organizationId`/`apiKey`/`client` are passed as options:
`costorahMiddleware({ apiKey, client, organizationId })`.

**Zero dependency on the `express` package itself** — the middleware's
request/response parameters are typed structurally
(`MinimalRequest`/`MinimalResponse`/`MinimalNextFunction`) against a
subset of Express's real types, so `@costorah/sdk` keeps its "zero
runtime dependencies" guarantee even with this integration installed.
`express`/`@types/express` are devDependencies used only to build a real
Express app in tests.

Source: `sdk/javascript/src/express.ts`, exported via the
`@costorah/sdk/express` subpath (`package.json`'s `exports` map, built
as a separate entry point by `tsup.config.ts`). Tests:
`sdk/javascript/tests/integrations/express.test.ts` (5 tests, using a
real `express()` app and `http.Server`).

## Shared mechanism: ambient request context

Both integrations are built on the same underlying primitive per
language — `costorah.context` (Python, `contextvars.ContextVar`) and
`context.ts` (JavaScript, `node:async_hooks`'s `AsyncLocalStorage`) —
which give per-request-async-chain isolated storage. `_submission.py` /
`submission.ts` merge this ambient context into every event's metadata,
additively, with zero effect when no framework integration is present
(existing manual `track()` and instrumentor behavior is unchanged).

## Planned, not yet built

The ticket named 19 framework integrations across Python and JavaScript.
Building all of them to genuine depth in a single pass was not feasible
without producing shallow stubs — the two above were chosen because
they're the ones named explicitly in the ticket's Success Criteria, and
because the underlying `context`/`_submission` mechanism they're built
on is now proven and directly reusable by every framework below without
further architectural work.

**Python** (planned, in the order they'd be built): Flask, Django,
Starlette (standalone, not via FastAPI), Celery, and the AI-framework
integrations — LangChain, LlamaIndex, CrewAI, AutoGen, MCP.

**JavaScript** (planned): NestJS, Next.js, Node.js (framework-agnostic
`http`/`https` helper), Cloudflare Workers, Vercel (Edge/Serverless
functions), AWS Lambda, Bun, Deno.

**AI framework auto-capture** (planned, both languages where
applicable): LangChain, LlamaIndex, CrewAI, AutoGen, Semantic Kernel,
Haystack — auto-capturing agent runs, chains, tool calls, memory
operations, latency, tokens, and cost, analogous to how EP-18.2's
provider instrumentors auto-capture LLM API calls today.

**Interactive configuration wizard** (planned): a `costorah init
--interactive` mode that detects the installed framework(s) and AI
SDK(s) and auto-generates a starter config, building on the
already-shipped detection logic in `costorah/cli.py`'s
`PROVIDER_PACKAGES`/`FRAMEWORK_PACKAGES` tables (currently surfaced via
plain `costorah init`/`costorah doctor` output, not yet an interactive
wizard).

Each of the above is a natural extension of the same
`request_context`/`set_default_client` pattern established here — adding
one is expected to be a small, self-contained change, not a redesign.
