"""
Ambient request context — lets a framework integration (FastAPI
middleware, etc.) attach request-scoped metadata (request ID, path,
method, organization) that automatically flows into every usage event
submitted during that request, without every instrumented call needing
to pass it explicitly.

Backed by `contextvars.ContextVar`, so it's correct under async
concurrency (each request's context is isolated even when requests are
handled concurrently on the same event loop) as well as across threads.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_request_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "costorah_request_context", default=None
)


def get_request_context() -> dict[str, Any] | None:
    """The current request's ambient metadata, or None outside a request
    (e.g. a background job, or no framework integration in use)."""
    return _request_context.get()


@contextmanager
def request_context(**fields: Any) -> Iterator[None]:
    """Sets ambient metadata for the duration of the `with` block. Framework
    middleware wraps each request in this; nothing else needs to call it
    directly under normal use."""
    token = _request_context.set(dict(fields))
    try:
        yield
    finally:
        _request_context.reset(token)
