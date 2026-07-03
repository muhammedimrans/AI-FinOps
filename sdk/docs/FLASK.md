# Flask Guide (EP-18.5)

## Install

```bash
pip install costorah flask
export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
```

## Quick start

```python
from flask import Flask
from costorah.integrations.flask import CostorahExtension

app = Flask(__name__)
CostorahExtension(app)
```

That's the entire integration. Combine with an instrumentor
(`from costorah.instrumentation import OpenAIInstrumentor;
OpenAIInstrumentor().instrument()`) and every request that makes an
OpenAI call gets automatic, request-tagged usage tracking with zero
per-view code.

## Application factory pattern

```python
from costorah.integrations.flask import CostorahExtension

ext = CostorahExtension()

def create_app():
    app = Flask(__name__)
    ext.init_app(app)
    return app
```

## Configuration

`CostorahExtension(app, api_key=..., client=..., organization_id=...)` —
all keyword-only, all optional. Without `api_key=`/`client=`, it reads
`COSTORAH_API_KEY`/`COSTORAH_ENDPOINT` from the environment. Without an
API key configured at all, the extension still installs (requests still
succeed), it just has nothing to submit usage to — a warning is logged
once.

## What gets captured

Per request: request ID (`X-Request-Id` header, or generated), path,
method, and — if `organization_id=` was passed — the organization. All
of it is attached to `metadata["request_context"]` on every usage event
captured while that request is being handled, and the request ID is
echoed back via an `X-Costorah-Request-Id` response header.

## Blueprints

Work automatically — no extra registration needed. `CostorahExtension`
wraps `app.wsgi_app` (below Flask's routing layer), so every blueprint's
routes are already covered once the extension is installed on the app.

## Multiple Flask apps in one process

Each `Flask` instance gets its own `CostorahExtension`/wrapped
`wsgi_app` and, if constructed with an explicit `client=`, its own
`Costorah` client — request context never leaks between apps. The one
piece of state that *is* process-global is
`costorah.instrumentation`'s "default client" (used by instrumentors
and by `_submission.submit()` when no explicit `client=` is given): if
two apps in the same process both auto-init from `COSTORAH_API_KEY`,
whichever app initialized last becomes the default. Pass an explicit
`client=` per app (and pass that same client explicitly wherever you'd
otherwise rely on the default) to avoid this when running multiple apps
with different credentials in one process.

## Under the hood

`CostorahExtension` is a thin wrapper around
`costorah.integrations.wsgi.CostorahWSGIMiddleware` — see `ASGI_WSGI.md`
for the lower-level middleware it delegates to, which is also directly
usable for Bottle, Pyramid, or any other WSGI application.

## Version compatibility

Targets Flask 2.0+. Below that, `costorah doctor` reports an advisory
(non-fatal) warning rather than refusing to run — see
`FRAMEWORK_INTEGRATIONS.md`'s compatibility matrix.

## Troubleshooting

- **No `X-Costorah-Request-Id` header on responses** — confirm
  `CostorahExtension(app)` (or `ext.init_app(app)`) actually ran before
  the app started serving requests; check application startup logs for
  a `costorah_wsgi_no_api_key` warning (logged by the underlying
  `CostorahWSGIMiddleware`) if usage isn't reaching COSTORAH.
- **Usage events not showing up in COSTORAH** — run `costorah doctor` to
  confirm SDK/Configuration/Connectivity/Authentication independently of
  Flask.
