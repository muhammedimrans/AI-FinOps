"""
CostorahMiddleware — Django integration (EP-18.5).

    MIDDLEWARE = [
        ...,
        "costorah.integrations.django.CostorahMiddleware",
    ]

Configuration is read from Django settings (`django.conf.settings`), not
constructor kwargs, since Django resolves `MIDDLEWARE` entries by dotted
path and instantiates them with only `get_response` — there's no
per-entry kwargs mechanism to hook into:

    COSTORAH_API_KEY = "costorah_live_..."          # or env COSTORAH_API_KEY
    COSTORAH_ENDPOINT = "https://api.costorah.com"  # optional
    COSTORAH_ORGANIZATION_ID = "org_123"             # optional

With `COSTORAH_API_KEY` set (in settings or the environment), this is
the entire integration. Per request it captures:

  - Request ID (`X-Request-Id` header, or generated)
  - Route (`request.path`) and method
  - The authenticated user's ID only — never the full user object,
    username, or email — read from `request.user.pk` when
    `request.user.is_authenticated` is True (both attributes are
    accessed defensively: apps without `AuthenticationMiddleware`
    installed simply get no user field, never an error)
  - Organization (from `COSTORAH_ORGANIZATION_ID`)
  - Latency (measured around the wrapped `get_response` call)
  - Errors (whether the view raised, and the exception's class name —
    never the exception message, which could contain request data)

Never captured: the request body, headers (beyond `X-Request-Id`),
cookies, or query string.

Works under both WSGI and ASGI deployment and both Django 4.x and 5.x,
using Django's documented dual sync/async middleware protocol.
"""

from __future__ import annotations

import importlib.metadata
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

from costorah._logging import get_logger
from costorah.context import request_context
from costorah.integrations._common import auto_init_client, check_min_version, generate_request_id

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

    from costorah.client import Costorah

try:
    import django  # noqa: F401 - import error is the actual check
except ImportError as exc:  # pragma: no cover - exercised only without django installed
    raise ImportError(
        "costorah.integrations.django requires 'django' to be installed. "
        "Install it with `pip install django` to use this integration."
    ) from exc

_log = get_logger(__name__)
_MIN_DJANGO_VERSION = (4, 0)

# Django's own middleware objects (HttpRequest/HttpResponse) are
# untyped (no py.typed marker), and `get_response` is sync in a WSGI
# deployment but a coroutine function in ASGI — rather than fight
# mypy's Union-of-Any-and-Awaitable handling for something the
# underlying framework doesn't type-check either, this is deliberately
# `Any`-typed at the boundary, same as the rest of this module's
# django.* interactions (see the mypy override in pyproject.toml).
GetResponse = Callable[[Any], Any]


def _build_client_from_settings() -> Costorah | None:
    """Prefers Django settings (`COSTORAH_API_KEY`/`COSTORAH_ENDPOINT`)
    over the environment, since settings.py is the idiomatic
    configuration surface for a Django app; falls back to
    `auto_init_client`'s environment-variable behavior (shared with
    every other integration) when settings don't define them."""
    from django.conf import settings as django_settings

    api_key = getattr(django_settings, "COSTORAH_API_KEY", None)
    endpoint = getattr(django_settings, "COSTORAH_ENDPOINT", None)
    if endpoint and not api_key:
        api_key = None  # let auto_init_client fall back to the env var
    if endpoint and api_key:
        from costorah.client import Costorah
        from costorah.exceptions import CostorahError

        try:
            return Costorah(api_key=api_key, endpoint=endpoint)
        except CostorahError as exc:
            _log.warning("costorah_django_init_failed error=%s", exc)
            return None
    return auto_init_client(api_key, integration_name="django")


def _organization_id_from_settings() -> str | None:
    from django.conf import settings as django_settings

    org_id = getattr(django_settings, "COSTORAH_ORGANIZATION_ID", None)
    return str(org_id) if org_id else None


def _user_id(request: HttpRequest) -> str | None:
    user = getattr(request, "user", None)
    if user is None:
        return None
    try:
        if not user.is_authenticated:
            return None
        return str(user.pk)
    except AttributeError:
        return None


class CostorahMiddleware:
    """Django dual sync/async middleware. Django instantiates this once
    per worker process at startup (not per request), so client
    construction and configuration reading happen once, in `__init__`."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: GetResponse) -> None:
        self.get_response = get_response
        # Own dispatch flag — kept separate from `_is_coroutine` below.
        # `markcoroutinefunction(self)` sets `self._is_coroutine` to
        # asgiref's sentinel marker object (not a bool), so reusing that
        # attribute name here would get silently overwritten by it.
        self._is_async_middleware = iscoroutinefunction(get_response)
        if self._is_async_middleware:
            markcoroutinefunction(self)

        installed_version = importlib.metadata.version("django")
        warning = check_min_version(
            installed_version, _MIN_DJANGO_VERSION, framework_name="Django"
        )
        if warning:
            _log.warning(warning)

        self._client = _build_client_from_settings()
        self._organization_id = _organization_id_from_settings()
        if self._client is not None:
            from costorah.instrumentation import set_default_client

            set_default_client(self._client)

    def _build_context(self, request: HttpRequest) -> tuple[str, dict[str, Any]]:
        request_id = request.headers.get("X-Request-Id") or generate_request_id()
        context: dict[str, Any] = {
            "request_id": request_id,
            "path": request.path,
            "method": request.method or "",
        }
        if self._organization_id:
            context["organization_id"] = self._organization_id
        user_id = _user_id(request)
        if user_id is not None:
            context["user_id"] = user_id
        return request_id, context

    def __call__(self, request: HttpRequest) -> Any:
        if self._is_async_middleware:
            return self.__acall__(request)
        return self.__sync_call__(request)

    def __sync_call__(self, request: HttpRequest) -> HttpResponse:
        request_id, context = self._build_context(request)
        start = time.perf_counter()
        try:
            with request_context(**context):
                response = self.get_response(request)
        except Exception as exc:
            _log_latency(start, error=exc)
            raise
        _log_latency(start, error=None)
        response["X-Costorah-Request-Id"] = request_id
        return response

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        request_id, context = self._build_context(request)
        start = time.perf_counter()
        try:
            with request_context(**context):
                response = await self.get_response(request)
        except Exception as exc:
            _log_latency(start, error=exc)
            raise
        _log_latency(start, error=None)
        response["X-Costorah-Request-Id"] = request_id
        return response


def _log_latency(start: float, *, error: BaseException | None) -> None:
    latency_ms = (time.perf_counter() - start) * 1000
    if error is not None:
        _log.debug(
            "costorah_django_request latency_ms=%.2f error=%s", latency_ms, type(error).__name__
        )
    else:
        _log.debug("costorah_django_request latency_ms=%.2f", latency_ms)
