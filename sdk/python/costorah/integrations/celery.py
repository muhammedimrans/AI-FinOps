"""
CostorahCelery — Celery integration (EP-18.5).

    from costorah.integrations.celery import CostorahCelery

    app = Celery("myapp")
    CostorahCelery(app)

With `COSTORAH_API_KEY` set in the environment, this is the entire
integration. Unlike the HTTP-framework integrations, Celery has no
per-request boundary to hook a middleware into — instead, this connects
to Celery's `task_prerun`/`task_postrun`/`task_retry`/`task_failure`
signals to bracket each task's execution in the same ambient
`costorah.context.request_context` mechanism the HTTP integrations use,
so any usage event captured *during* a task (e.g. an instrumented OpenAI
call made inside the task body) is automatically tagged with that task's
ID, name, queue (routing key), and worker hostname — the Celery
equivalent of "request ID, path, method" for an HTTP request.

Captured per task: task ID (as the ambient request ID), task name,
queue, worker hostname, duration, retry count, and — on failure — the
exception's class name only. Never captured: task arguments/kwargs
(`task_failure`'s signal payload includes them; this integration
deliberately never reads or logs them) or the task's return value.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from costorah._logging import get_logger
from costorah.context import request_context
from costorah.integrations._common import auto_init_client

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

    from costorah.client import Costorah

try:
    import celery  # noqa: F401 - import error is the actual check
    from celery.signals import task_failure, task_postrun, task_prerun, task_retry
except ImportError as exc:  # pragma: no cover - exercised only without celery installed
    raise ImportError(
        "costorah.integrations.celery requires 'celery' to be installed. "
        "Install it with `pip install celery` to use this integration."
    ) from exc

_log = get_logger(__name__)


class CostorahCelery:
    def __init__(
        self,
        app: Any,
        *,
        api_key: str | None = None,
        client: Costorah | None = None,
        organization_id: str | None = None,
    ) -> None:
        self.app = app
        self._organization_id = organization_id
        self._client = (
            client if client is not None else auto_init_client(api_key, integration_name="celery")
        )
        if self._client is not None:
            from costorah.instrumentation import set_default_client

            set_default_client(self._client)

        # task_id -> (open request_context manager, start time). Entered
        # in task_prerun, exited in task_postrun — Celery runs both
        # signals and the task body synchronously in the same thread (in
        # every pool implementation: prefork, solo, eventlet, gevent),
        # so this correctly brackets the task's execution the same way
        # `with request_context(...):` would if Celery gave us a single
        # call site to wrap.
        self._active: dict[str, tuple[AbstractContextManager[None], float]] = {}

        task_prerun.connect(self._on_prerun, weak=False)
        task_postrun.connect(self._on_postrun, weak=False)
        task_retry.connect(self._on_retry, weak=False)
        task_failure.connect(self._on_failure, weak=False)

    def _on_prerun(
        self, sender: Any = None, task_id: str | None = None, task: Any = None, **_kwargs: Any
    ) -> None:
        if task_id is None:
            return
        context: dict[str, Any] = {
            "request_id": task_id,
            "task_name": getattr(task or sender, "name", None) or "",
        }
        request = getattr(task, "request", None)
        if request is not None:
            delivery_info = getattr(request, "delivery_info", None) or {}
            queue = delivery_info.get("routing_key")
            if queue:
                context["queue"] = queue
            hostname = getattr(request, "hostname", None)
            if hostname:
                context["worker"] = hostname
        if self._organization_id:
            context["organization_id"] = self._organization_id

        cm = request_context(**context)
        cm.__enter__()
        self._active[task_id] = (cm, time.perf_counter())

    def _on_postrun(
        self,
        sender: Any = None,
        task_id: str | None = None,
        task: Any = None,
        state: str | None = None,
        **_kwargs: Any,
    ) -> None:
        if task_id is None:
            return
        entry = self._active.pop(task_id, None)
        if entry is None:
            return
        cm, start = entry
        cm.__exit__(None, None, None)
        duration_ms = (time.perf_counter() - start) * 1000
        task_name = getattr(task or sender, "name", None) or ""
        _log.debug(
            "costorah_celery_task_complete task=%s state=%s duration_ms=%.2f",
            task_name,
            state,
            duration_ms,
        )

    def _on_retry(
        self, sender: Any = None, request: Any = None, reason: Any = None, **_kwargs: Any
    ) -> None:
        task_name = getattr(sender, "name", None) or ""
        # `reason` is typically the exception that triggered the retry —
        # only its class name is logged, never str(reason), which could
        # echo back task argument values embedded in a custom exception.
        _log.debug(
            "costorah_celery_task_retry task=%s reason_type=%s", task_name, type(reason).__name__
        )

    def _on_failure(
        self,
        sender: Any = None,
        task_id: str | None = None,
        exception: Any = None,
        **_kwargs: Any,
    ) -> None:
        # task_failure's signal payload includes the task's original
        # args/kwargs — deliberately not read here.
        task_name = getattr(sender, "name", None) or ""
        _log.debug(
            "costorah_celery_task_failure task=%s task_id=%s error=%s",
            task_name,
            task_id,
            type(exception).__name__,
        )
