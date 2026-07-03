# Celery Guide (EP-18.5)

## Install

```bash
pip install costorah celery
export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
```

## Quick start

```python
from celery import Celery
from costorah.integrations.celery import CostorahCelery

app = Celery("myapp")
CostorahCelery(app)
```

Combine with an instrumentor
(`from costorah.instrumentation import OpenAIInstrumentor;
OpenAIInstrumentor().instrument()`) and any OpenAI call made *inside* a
task body gets automatic usage tracking, tagged with that task's
context — with zero code inside the task itself.

## How it works

Celery has no single call site to wrap the way HTTP frameworks have "one
request → one middleware call" — a task's execution is bracketed by
separate `task_prerun` and `task_postrun` signals. `CostorahCelery`
connects to both (plus `task_retry` and `task_failure`) and manually
enters/exits `costorah.context.request_context(...)` around each task's
execution, so any usage event captured during the task inherits that
context, exactly like the HTTP integrations' request context.

This is correct because `task_prerun`, the task body, and `task_postrun`
all execute synchronously in the same thread under every Celery pool
implementation (prefork, solo, eventlet, gevent) — there's no reordering
or cross-thread hazard for the `contextvars`-based mechanism to worry
about.

## What gets captured

Per task: task ID (as the ambient request ID), task name, queue
(delivery routing key, when available), worker hostname (when
available), and the configured organization. Duration is measured
around the prerun→postrun span and logged (not currently submitted as a
usage event — see "What this doesn't do" below).

On retry: the retry-triggering exception's **class name only** — never
`str(reason)`, since a custom retry exception could embed task argument
values.

On failure: the failing exception's **class name only**. Celery's
`task_failure` signal payload includes the task's original `args`/
`kwargs` — this integration deliberately never reads them.

## What this doesn't do

`CostorahCelery` does not submit a `client.track()` usage event *for the
task itself* — COSTORAH's `track()` API models AI provider usage
(provider, model, tokens, cost), which a generic Celery task doesn't
have. What it submits instead is *ambient context* that any usage event
captured **inside** the task (via an instrumented provider SDK call, or
a manual `client.track()` call) automatically inherits. If you want
task-level telemetry independent of any AI provider call, that's outside
this integration's scope.

## Version compatibility

Targets Celery 5.3+. Below that, `costorah doctor` reports an advisory
(non-fatal) warning rather than refusing to run — see
`FRAMEWORK_INTEGRATIONS.md`'s compatibility matrix.

## Troubleshooting

- **Usage events from inside a task have no `task_name`/`queue` in their
  context** — confirm `CostorahCelery(app)` runs once at worker startup
  (not per-task) and before any tasks are registered/executed; check for
  a `costorah_celery_no_api_key`-style warning in worker startup logs.
- **Testing locally** — Celery's `task_always_eager = True` config
  setting still fires `task_prerun`/`task_postrun`, so
  `CostorahCelery`'s context capture works the same way under eager
  execution as it does against a real worker/broker (used throughout
  this integration's own test suite).
