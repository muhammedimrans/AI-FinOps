# Django Guide (EP-18.5)

## Install

```bash
pip install costorah django
```

## Quick start

```python
# settings.py
MIDDLEWARE = [
    ...,
    "costorah.integrations.django.CostorahMiddleware",
]

COSTORAH_API_KEY = "costorah_live_xxxxxxxxx"      # or set env COSTORAH_API_KEY
```

That's the entire integration. Combine with an instrumentor
(`from costorah.instrumentation import OpenAIInstrumentor;
OpenAIInstrumentor().instrument()`, typically in your `AppConfig.ready()`)
and every request that makes an OpenAI call gets automatic,
request-tagged usage tracking with zero per-view code.

## Configuration

Read from `django.conf.settings`, not middleware constructor arguments —
Django's `MIDDLEWARE` list instantiates each entry with only
`get_response`, so there's no per-entry kwargs mechanism to hook into:

| Setting | Purpose |
|---|---|
| `COSTORAH_API_KEY` | falls back to the `COSTORAH_API_KEY` env var if unset |
| `COSTORAH_ENDPOINT` | falls back to `COSTORAH_ENDPOINT` env var, then `https://api.costorah.com` |
| `COSTORAH_ORGANIZATION_ID` | optional, attached to every request's context |

## What gets captured

Per request: request ID (`X-Request-Id` header, or generated), route
(`request.path`), method, the **authenticated user's ID only**, the
configured organization, latency, and — on an unhandled view exception —
the exception's class name.

The user ID is read defensively: `request.user.is_authenticated` and
`request.user.pk`, never the full user object, username, or email. Apps
that don't install `django.contrib.auth.middleware.
AuthenticationMiddleware` simply get no `user_id` field in the captured
context — never an error.

Never captured: the request body, headers beyond `X-Request-Id`,
cookies, or query string.

## ASGI and WSGI

`CostorahMiddleware` is written using Django's documented dual sync/
async middleware protocol (`sync_capable = async_capable = True`,
detecting whether the next middleware in the chain is a coroutine
function via `asgiref.sync.iscoroutinefunction` and marking itself
accordingly via `markcoroutinefunction`). The same `MIDDLEWARE` entry
works unmodified whether the app is deployed under `manage.py runserver`
/ a WSGI server (gunicorn, uWSGI) or an ASGI server (uvicorn, daphne).

## Management command

Adding `"costorah.integrations.django"` to `INSTALLED_APPS` registers:

```bash
python manage.py costorah_doctor
python manage.py costorah_doctor --timeout 5
```

which runs the same SDK/Configuration/Connectivity/Authentication/
Framework/Provider checks as `costorah doctor` from the shell (reusing
`costorah.cli.run_doctor` directly — no duplicated check logic), with
one Django-specific addition: `COSTORAH_API_KEY`/`COSTORAH_ENDPOINT` are
read from `django.conf.settings` first, falling back to the environment,
matching the middleware's own configuration precedence. Exits non-zero
if any check fails, same as the shell command.

## Version compatibility

Targets Django 4.0+ and 5.x. Below that, `costorah doctor` (and
`costorah_doctor`) report an advisory (non-fatal) warning rather than
refusing to run — see `FRAMEWORK_INTEGRATIONS.md`'s compatibility
matrix.

## Troubleshooting

- **`user_id` never appears in captured context** — confirm
  `django.contrib.auth.middleware.AuthenticationMiddleware` runs
  *before* `CostorahMiddleware` in `MIDDLEWARE` (Django applies request
  middleware top-to-bottom), and that the request is actually
  authenticated.
- **`manage.py costorah_doctor: command not found`** — add
  `"costorah.integrations.django"` to `INSTALLED_APPS`; the middleware
  entry alone doesn't register the management command.
- **Usage events not showing up in COSTORAH** — run
  `manage.py costorah_doctor` to confirm SDK/Configuration/Connectivity/
  Authentication independently of any particular view.
