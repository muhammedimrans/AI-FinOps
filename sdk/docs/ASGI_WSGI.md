# Generic ASGI / WSGI Guide (EP-18.5)

For any ASGI or WSGI application this SDK doesn't have a named
integration for (Quart, Falcon, Litestar, Bottle, Pyramid, and so on) —
and the same underlying middleware `costorah.integrations.flask`'s
`CostorahExtension` wraps internally.

## ASGI

```python
from costorah.integrations.asgi import CostorahASGIMiddleware

app = CostorahASGIMiddleware(app, api_key=..., client=..., organization_id=...)
```

Wraps a raw ASGI 3 application (`async def app(scope, receive, send)`,
or any object implementing that protocol). Only `http`-type scopes are
touched — `lifespan` and `websocket` scopes pass through completely
unmodified.

## WSGI

```python
from costorah.integrations.wsgi import CostorahWSGIMiddleware

app = CostorahWSGIMiddleware(app, api_key=..., client=..., organization_id=...)
```

Wraps a raw WSGI application (`def app(environ, start_response)`).

## Both, identically

- Auto-initialize a `Costorah` client from `COSTORAH_API_KEY`/
  `COSTORAH_ENDPOINT` (or explicit `api_key=`/`client=`), wiring it as
  the default client every `costorah.instrumentation.*` instrumentor
  submits through.
- Capture request context — request ID (`X-Request-Id` header, or
  generated), path, method, optional `organization_id` — attached to
  every usage event captured during that request/scope.
- Echo the request ID back via an `X-Costorah-Request-Id` response
  header.
- Degrade gracefully with no API key configured: one warning is logged,
  requests still succeed, nothing is submitted.

## Zero framework dependency

Both middleware classes are written against the raw ASGI/WSGI protocols
only — no import of Quart, Falcon, Litestar, Bottle, Pyramid, or any
other framework, and no dependency on Starlette/Flask either (those get
their own richer, framework-native integrations — see
`FRAMEWORK_INTEGRATIONS.md`). This is why they're directly testable
against a hand-rolled minimal ASGI/WSGI app with no framework installed
at all — see `sdk/python/tests/integrations/test_asgi_middleware.py` and
`test_wsgi_middleware.py`.

## When to use the named integration instead

If you're on FastAPI, Starlette, Flask, or Django, use
`costorah.integrations.fastapi`/`.starlette`/`.flask`/`.django` instead
— they're built on top of these same primitives but integrate more
natively with each framework's own conventions (e.g. Django reads
configuration from `settings.py`; Flask supports the application-factory
pattern and blueprints explicitly).
