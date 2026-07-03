# Framework Integrations (EP-18.4, EP-18.5)

## Built

EP-18.4 built FastAPI (Python) and Express (JavaScript) — the two named
in that ticket's Success Criteria. EP-18.5 extended the Python side with
Flask, Django, Starlette (standalone), Celery, and generic ASGI/WSGI
middleware — every Python integration named in the EP-18.5 ticket, all
built to full, tested depth (no placeholders), all reusing the same
`costorah.context` ambient-request-context mechanism FastAPI introduced
rather than duplicating request-handling logic per framework.

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

### Python: Flask

```python
from flask import Flask
from costorah.integrations.flask import CostorahExtension

app = Flask(__name__)
CostorahExtension(app)
```

Also supports the application-factory pattern (`ext = CostorahExtension();
ext.init_app(app)`). Internally wraps `app.wsgi_app` with
`costorah.integrations.wsgi.CostorahWSGIMiddleware` — no duplicate
request-handling logic. Works across blueprints (routing happens above
the WSGI layer this wraps) and multiple independent `Flask` instances in
one process; see the module docstring for the one piece of state that
*is* process-global (`costorah.instrumentation`'s default client — same
caveat as FastAPI/Express).

Source: `sdk/python/costorah/integrations/flask.py`. Tests:
`sdk/python/tests/integrations/test_flask_extension.py` (5 tests — direct
init, application factory, blueprints, multi-app isolation, graceful
degradation). Full guide: `sdk/docs/FLASK.md`.

### Python: Django

```python
MIDDLEWARE = [
    ...,
    "costorah.integrations.django.CostorahMiddleware",
]
```

Configuration is read from Django settings (`COSTORAH_API_KEY`,
`COSTORAH_ENDPOINT`, `COSTORAH_ORGANIZATION_ID`), not constructor
kwargs — Django's `MIDDLEWARE` list only instantiates entries with
`get_response`. Supports both WSGI and ASGI deployment via Django's
documented dual sync/async middleware protocol (`asgiref.sync.
iscoroutinefunction`/`markcoroutinefunction`), Django 4.x and 5.x.
Captures request ID, route, method, the **authenticated user's ID only**
(never the full user object — read defensively via
`request.user.is_authenticated`/`.pk`, with apps that don't install
`AuthenticationMiddleware` simply getting no user field, never an
error), organization, latency, and — on an unhandled view exception —
the exception's class name (never its message). Never captures the
request body, headers beyond `X-Request-Id`, cookies, or query string.

Adding `"costorah.integrations.django"` to `INSTALLED_APPS` additionally
registers a `manage.py costorah_doctor` management command, which reuses
`costorah.cli.run_doctor` (no duplicate check logic) with one addition:
it reads `COSTORAH_API_KEY`/`COSTORAH_ENDPOINT` from Django settings
first, falling back to the environment.

Source: `sdk/python/costorah/integrations/django/` (`middleware.py`,
`apps.py`, `management/commands/costorah_doctor.py`). Tests:
`sdk/python/tests/integrations/test_django_middleware.py` (6 tests —
sync, async, user-ID capture, anonymous/no-auth-middleware degradation,
exception handling) and `test_django_management_command.py` (2 tests).
Full guide: `sdk/docs/DJANGO.md`.

### Python: Starlette (standalone)

```python
from starlette.applications import Starlette
from costorah.integrations.starlette import CostorahMiddleware

app = Starlette()
app.add_middleware(CostorahMiddleware)
```

`costorah.integrations.starlette.CostorahMiddleware` **is**
`costorah.integrations.fastapi.CostorahMiddleware` — a deliberate
re-export, not a copy, since FastAPI *is* a Starlette application and
the middleware never touches anything FastAPI-specific. This exists so
plain-Starlette users get an import path matching their framework's
name.

Source: `sdk/python/costorah/integrations/starlette.py`. Tests:
`sdk/python/tests/integrations/test_starlette_middleware.py` (2 tests —
one of which asserts the re-export identity directly).

### Python: Celery

```python
from costorah.integrations.celery import CostorahCelery

app = Celery("myapp")
CostorahCelery(app)
```

Celery has no per-request boundary to hook a middleware into, so this
connects to Celery's `task_prerun`/`task_postrun`/`task_retry`/
`task_failure` signals instead, bracketing each task's execution in the
same `costorah.context.request_context` mechanism the HTTP integrations
use — any usage event captured *during* a task (e.g. an instrumented
OpenAI call inside the task body) is automatically tagged with that
task's ID (as the ambient request ID), name, queue (routing key), and
worker hostname. Retries log the triggering exception's class name only
(never `str(reason)`, which could echo back task argument values from a
custom exception); failures log the exception's class name only — task
`args`/`kwargs` from the `task_failure` signal's payload are never read.

Source: `sdk/python/costorah/integrations/celery.py`. Tests:
`sdk/python/tests/integrations/test_celery_integration.py` (5 tests,
using `task_always_eager` — context capture, context clearing after
completion, isolation across sequential tasks, failure handling,
graceful degradation). Full guide: `sdk/docs/CELERY.md`.

### Python: generic ASGI / WSGI

```python
from costorah.integrations.asgi import CostorahASGIMiddleware
app = CostorahASGIMiddleware(app)   # Quart, Falcon, Litestar, ...

from costorah.integrations.wsgi import CostorahWSGIMiddleware
app = CostorahWSGIMiddleware(app)   # Bottle, Pyramid, ...
```

Raw ASGI-3 and WSGI middleware with **zero dependency on any specific
framework** — these are what `costorah.integrations.flask` wraps
internally, and are directly usable standalone for any ASGI or WSGI
application this EP didn't build a named integration for. Same
behavior as every other integration: auto-init from `COSTORAH_API_KEY`,
request context capture, `X-Costorah-Request-Id` response header,
graceful degradation with no API key.

Source: `sdk/python/costorah/integrations/asgi.py`,
`sdk/python/costorah/integrations/wsgi.py`. Tests:
`test_asgi_middleware.py` (3 tests, against a hand-rolled ASGI app — no
framework dependency needed to test it) and `test_wsgi_middleware.py` (3
tests, against a hand-rolled WSGI app). Full guide:
`sdk/docs/ASGI_WSGI.md`.

## Shared helpers (`costorah.integrations._common`)

Every Python integration above shares three small helpers instead of
each reimplementing them: `auto_init_client()` (build a `Costorah`
client from an explicit key or `COSTORAH_API_KEY`, returning `None`
rather than raising if unconfigured), `generate_request_id()`, and
`check_min_version()`/`parse_version()` (the same graceful,
never-raising "below this floor, may still work but is untested"
version-compatibility check used by `costorah doctor`'s Framework
version compatibility check — see `CLI.md`).

## Shared mechanism: ambient request context

Both integrations are built on the same underlying primitive per
language — `costorah.context` (Python, `contextvars.ContextVar`) and
`context.ts` (JavaScript, `node:async_hooks`'s `AsyncLocalStorage`) —
which give per-request-async-chain isolated storage. `_submission.py` /
`submission.ts` merge this ambient context into every event's metadata,
additively, with zero effect when no framework integration is present
(existing manual `track()` and instrumentor behavior is unchanged).

## Compatibility matrix

| Framework | Minimum version | Enforced by |
|---|---|---|
| FastAPI | 0.100 | `costorah doctor`'s Framework version compatibility check |
| Flask | 2.0 | same |
| Django | 4.0 | same |
| Starlette | 0.27 | same |
| Celery | 5.3 | same |
| Python | 3.9+ | `pyproject.toml`'s `requires-python` |

A below-minimum installed version is reported as an **advisory**
warning (`costorah doctor` output, non-fatal — doesn't flip the exit
code) rather than an error: the framework may well still work, this
just means it's untested below that floor. See
`costorah.integrations._common.check_min_version` and `CLI.md`.

## JavaScript integrations (EP-18.6)

EP-18.6 built every framework/runtime named in its ticket, all Python's
`request_context`/`set_default_client` pattern's exact JS-side
equivalent (`runWithRequestContext`/`setDefaultClient`) reused rather
than reimplemented per integration:

- **NestJS** (`@costorah/sdk/nest`) — `CostorahModule.forRoot()`,
  `CostorahInterceptor`, `CostorahMiddleware`, `@InjectCostorah()`. See
  `NESTJS.md`.
- **Next.js** (`@costorah/sdk/next`) — `costorahHandler` (App Router
  Route Handlers + Middleware, Edge Runtime), `costorahApiRoute` (Pages
  Router). Server Actions explicitly not wrapped (no `Request` object
  exists to attach context to) — see `NEXTJS.md`.
- **Cloudflare Workers** (`@costorah/sdk/cloudflare`) —
  `costorahWorker`, supporting both a plain `fetch` handler and a full
  `ExportedHandler` object (Pages Functions, Durable Objects). Reads
  configuration from Workers `env` bindings, not `process.env` — see
  `CLOUDFLARE_WORKERS.md`.
- **AWS Lambda** (`@costorah/sdk/lambda`) — `costorahLambda`, detecting
  API Gateway v1/v2, ALB, and passing EventBridge/SQS/SNS events through
  with ambient-context-only capture. Reuses a client across warm
  invocations — see `AWS_LAMBDA.md`.
- **Generic Node.js** (`@costorah/sdk/node`) — `costorahNodeMiddleware`,
  for standalone `http`/`https` servers and anything without a
  framework. What `costorahMiddleware` (Express) and NestJS's
  `CostorahMiddleware` both delegate to internally — see `NODE.md`.
- **Bun** — verified by actually running the built package under a real
  Bun runtime in this EP (not just reasoning about compatibility); no
  Bun-specific integration code needed — see `BUN.md`.
- **Deno** — assessed via code review only (Deno wasn't available in
  this EP's build environment); documented as "should work, unverified"
  rather than claimed as tested — see `DENO.md`.
- **Runtime detection** (`detectRuntime`/`detectRuntimeVersion`/
  `detectFrameworks`, exported from `@costorah/sdk`'s main entry) — see
  `RUNTIME_COMPATIBILITY.md`.

See `RUNTIME_COMPATIBILITY.md` for the full runtime/framework
compatibility matrix.

## Planned, not yet built

**AI framework auto-capture** (explicitly out of scope for EP-18.4,
EP-18.5, and EP-18.6): LangChain, LlamaIndex, CrewAI, AutoGen, Semantic
Kernel, Haystack, MCP — auto-capturing agent runs, chains, tool calls,
memory operations, latency, tokens, and cost, analogous to how EP-18.2's
provider instrumentors auto-capture LLM API calls today.

**Interactive configuration wizard** (planned, Python-side): a
`costorah init --interactive` mode that detects the installed
framework(s) and AI SDK(s) and auto-generates a starter config, building
on the already-shipped detection logic in `costorah/cli.py`'s
`PROVIDER_PACKAGES`/`FRAMEWORK_PACKAGES` tables. No JavaScript
equivalent exists or is planned, since the JS SDK has no CLI binary at
all — see `RUNTIME_COMPATIBILITY.md`'s "What's different from the
Python CLI."

Each of the above is a natural extension of the same
`request_context`/`set_default_client` pattern established here — adding
one is expected to be a small, self-contained change, not a redesign.
