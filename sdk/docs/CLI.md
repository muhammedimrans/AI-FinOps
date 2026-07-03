# `costorah` CLI (EP-18.4)

Installed automatically with the Python SDK (`pip install costorah`) via
the `costorah` console script (`sdk/python/pyproject.toml`'s
`[project.scripts]`). JavaScript-only projects don't get a separate CLI
binary in this EP — `costorah doctor`/`init` work against any project
with `COSTORAH_API_KEY` set, regardless of which SDK the app itself
uses, since they only need the Python SDK installed to run the checks.

Every subcommand is implemented as a small, independently-testable
`run_*` function in `sdk/python/costorah/cli.py`, fully decoupled from
argument parsing/printing — `main()` is a thin wiring layer. All
behavior below is exercised by `sdk/python/tests/test_cli.py` (18
tests).

## `costorah version`

Prints the installed SDK version.

```
$ costorah version
costorah 1.0.0
```

Exit code: always `0`.

## `costorah config`

Prints resolved configuration as JSON, with the API key masked
(`costorah_live_ab...wxyz`) — never printed in full.

```
$ costorah config
{
  "api_key": "costorah_live_ab...wxyz",
  "api_key_set": true,
  "endpoint": "https://api.costorah.com",
  "sdk_version": "1.0.0"
}
```

Exit code: always `0`.

## `costorah init`

Detects your environment — whether `COSTORAH_API_KEY` is set, which
supported AI provider SDKs are installed (`openai`, `anthropic`,
`google-genai`, `mistralai`, `cohere`, `boto3`), and which supported web
frameworks are installed (`fastapi`, `flask`, `django`, `starlette`,
`celery`) — and prints tailored next steps.

```
$ costorah init
API key configured: no
Detected frameworks: fastapi
Detected AI providers: openai

Next steps:
  - Set COSTORAH_API_KEY (Organization API Key from the COSTORAH dashboard, prefixed costorah_live_...).
  - Detected openai installed — instrument with e.g. `from costorah.instrumentation import OpenAIInstrumentor` (see sdk/docs/AUTOMATIC_INSTRUMENTATION.md for openai's instrumentor name).
  - FastAPI/Starlette detected — add `app.add_middleware(CostorahMiddleware)` (from costorah.integrations.fastapi) for automatic request context.
  - Run `costorah doctor` to verify the integration end-to-end.
```

As of EP-18.5, Flask, Django, Starlette, and Celery all have dedicated
integrations (`costorah.integrations.flask`/`.django`/`.starlette`/
`.celery` — see `FRAMEWORK_INTEGRATIONS.md`), so detection for all five
Python frameworks now maps to real, working middleware.

Exit code: always `0`.

## `costorah doctor`

The Success Criteria check from the EP-18.4 ticket. Validates, in order:

| Check | What it verifies |
|---|---|
| SDK import | always passes — if this runs, the SDK imported |
| Configuration | `COSTORAH_API_KEY` is set and starts with `costorah_live_` |
| Connectivity | a real `track()` + `flush()` round-trip reached the endpoint |
| Authentication | the endpoint accepted (vs. rejected) the check event |
| Framework detection | which supported frameworks are installed |
| Framework version compatibility | (EP-18.5, zero or more entries) each detected framework below its supported-version floor — see `FRAMEWORK_INTEGRATIONS.md`'s compatibility matrix |
| Provider detection | which supported AI provider SDKs are installed |

Framework version compatibility entries are **advisory** — reported with
`ok=True` even when a below-floor version is found, so an old-but-working
framework version never flips `doctor`'s exit code. This matches every
integration's "unsupported version is a graceful degrade, not a crash"
policy (`costorah.integrations._common.check_min_version`).

Connectivity/Authentication are verified with one real, best-effort
`track()` call (a `costorah_doctor_check` no-op event with `cost=0.0`) —
never fabricated. The classification logic distinguishes three real
outcomes using the reliability layer's queue stats
(`sent_total`/`retry_count`/`failed_total`, see `RELIABILITY.md`):

- **Delivered** (`sent_total > 0`): Connectivity ✓, Authentication ✓.
- **Permanently rejected** (`retry_count == 0 and failed_total > 0`): the
  endpoint responded with a non-retryable status (400/401/403/404) —
  Connectivity ✓ (it *did* respond), Authentication ✗.
- **No confirmed response** (anything else, e.g. still retrying a
  network error or 5xx/429/408 when `--timeout` elapses): Connectivity
  ✗, Authentication skipped.

```
$ costorah doctor
  ✓ SDK import: costorah 1.0.0
  ✓ Configuration: COSTORAH_API_KEY is set and well-formed
  ✓ Connectivity: reached https://api.costorah.com
  ✓ Authentication: API key accepted
  ✓ Framework detection: detected: fastapi, flask, django, starlette, celery
  ✓ Provider detection: detected: openai

All checks passed.
```

If any detected framework is below its supported-version floor, a
`Framework version compatibility` line appears per below-floor
framework (still `✓`, since it's advisory):

```
  ✓ Framework version compatibility: costorah's flask integration targets flask >=2.0; detected 1.9. It may still work, but is untested below that version.
```

Flags: `--timeout <seconds>` (default `10.0`) — how long to wait for a
confirmed connectivity/auth result before reporting "no confirmed
response."

Exit code: `0` if every check passed, `1` otherwise.

## `costorah health`

Constructs a real client from `COSTORAH_API_KEY`/`COSTORAH_ENDPOINT` and
prints its live `health()` + `queue_stats()` snapshot as JSON — useful
for confirming the background worker, circuit breaker, and queue are in
the expected state outside of a full `doctor` run.

```
$ costorah health
{
  "worker": "running",
  "circuit_breaker": "closed",
  ...
  "queue_stats": { "queue_depth": 0, "sent_total": 0, "failed_total": 0, "retry_count": 0 }
}
```

Prints `{"error": "..."}` and exits `1` if `COSTORAH_API_KEY` is unset
or client construction fails.

Flags: `--timeout <seconds>` (default `5.0`).

Exit code: `0` on success, `1` if `"error"` is present in the output.
