"""
MCPInstrumentor — automatic Model Context Protocol client/server
observability (EP-18.7).

    from costorah.instrumentation.mcp import MCPInstrumentor

    MCPInstrumentor().instrument()

    async with ClientSession(read, write) as session:
        await session.call_tool("search", {"query": "..."})   # timing,
                                                                # success/
                                                                # failure,
                                                                # and tool
                                                                # name are
                                                                # captured
                                                                # automatically

## Why this instrumentor never submits a usage event

Every other AI-framework instrumentor in this package
(`costorah.instrumentation.langchain`, `.crewai`) submits real usage
events through the existing `costorah.instrumentation._submission`
pipeline for actual completed LLM calls — provider/model/token/cost
shaped, matching the backend's ingestion schema
(`costorah.types.SUPPORTED_PROVIDERS`). MCP tool calls, resource reads,
and prompt fetches are **not** LLM calls — they carry no token counts,
no cost, and no LLM provider. Inventing a fake "mcp" provider or
zero-cost usage record to force them into that schema would misrepresent
real spend data, so this instrumentor never does that. Instead, it
captures structured, local telemetry only: `events_captured_total`
(a running count) plus debug-level structured log lines with
tool/resource/prompt name, duration, and success/failure — the same
"local logging/counting, not invented submission" treatment
`costorah.instrumentation.crewai` gives its non-LLM lifecycle events.

If an MCP tool call happens to trigger a downstream LLM call (e.g. an
MCP server that itself calls out to an LLM), that call is captured by
whatever provider or AI-framework instrumentor is actually instrumenting
*that* call site — not by this one.

## What gets captured

Client side (`mcp.ClientSession`): `call_tool`, `read_resource`,
`get_prompt`, `list_tools`, `list_resources`, `list_prompts` are each
wrapped with timing + success/failure capture. The tool/resource/prompt
*name* being called is captured (needed to know what was invoked at
all); ambient `costorah.context.request_context(mcp_tool_name=...)` is
entered for the duration of a `call_tool` (safe here — MCP client calls
are single `await`s on the calling task, not dispatched across a
thread-pool the way `costorah.instrumentation.crewai`'s events are, so
context propagates and unwinds correctly with ordinary
`contextvars` semantics).

Server side (`mcp.server.lowlevel.Server`): the `call_tool()`,
`read_resource()`, and `get_prompt()` decorator factories are wrapped so
that whatever handler function gets registered through them is timed the
same way, without altering the handler's return value or error
behavior. Because these are decorator factories applied at handler
*registration* time, `MCPInstrumentor().instrument()` must run **before**
`@server.call_tool()` etc. are applied — the same ordering requirement
every other instrumentor/middleware in this SDK has (e.g.
`CostorahExtension(app)` must wrap a Flask app before its routes are
registered). Calling `instrument()` after a server has already
registered its handlers silently instruments nothing on the server side
(verified empirically — the client-side wrapping is unaffected either
way, since it patches `ClientSession` methods directly rather than
per-call registrations).

## Never captured

Tool call arguments, tool call results, resource contents, and prompt
contents/arguments are never read, logged, or transmitted by this
instrumentor — only the name being invoked, duration, and whether it
raised. Transport/session identity (e.g. the underlying stdio/SSE/HTTP
connection) is not separately captured beyond what's already visible via
`request_context()`'s existing request/trace ID propagation.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from costorah._logging import get_logger
from costorah.context import request_context

try:
    from mcp import ClientSession
    from mcp.server.lowlevel import Server
except ImportError as exc:  # pragma: no cover - exercised only without mcp installed
    raise ImportError(
        "costorah.instrumentation.mcp requires the 'mcp' package to be installed. "
        "Install it with `pip install mcp` to use this instrumentor."
    ) from exc

_log = get_logger(__name__)

_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])

_CLIENT_METHODS_WITH_NAME_ARG: tuple[str, ...] = ("call_tool", "read_resource", "get_prompt")
_CLIENT_METHODS_WITHOUT_NAME_ARG: tuple[str, ...] = (
    "list_tools",
    "list_resources",
    "list_prompts",
)
_SERVER_DECORATOR_METHODS: tuple[str, ...] = ("call_tool", "read_resource", "get_prompt")


class _MCPTelemetryState:
    """Holds the running counter and original (unpatched) method
    references so `uninstrument()` can restore them exactly."""

    def __init__(self) -> None:
        self.events_captured_total = 0
        self._client_originals: dict[str, Callable[..., Any]] = {}
        self._server_originals: dict[str, Callable[..., Any]] = {}

    def record(self, *, kind: str, name: str | None, duration_ms: float, success: bool) -> None:
        self.events_captured_total += 1
        _log.debug(
            "mcp_%s name=%s duration_ms=%.2f success=%s",
            kind,
            name,
            duration_ms,
            success,
        )


def _name_from_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    if kwargs.get("name") is not None:
        return str(kwargs["name"])
    if kwargs.get("uri") is not None:
        return str(kwargs["uri"])
    if args:
        return str(args[0])
    return None


def _wrap_client_method(
    original: Callable[..., Awaitable[Any]],
    *,
    kind: str,
    state: _MCPTelemetryState,
    enrich_context: bool,
) -> Callable[..., Awaitable[Any]]:
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        name = _name_from_args(args, kwargs)
        cm = None
        if enrich_context and name is not None:
            cm = request_context(mcp_tool_name=name)
            cm.__enter__()
        start = time.perf_counter()
        success = True
        try:
            return await original(self, *args, **kwargs)
        except Exception:
            success = False
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            state.record(kind=kind, name=name, duration_ms=duration_ms, success=success)
            if cm is not None:
                cm.__exit__(None, None, None)

    wrapper.__name__ = getattr(original, "__name__", kind)
    wrapper.__doc__ = original.__doc__
    return wrapper


def _wrap_server_decorator(
    original_decorator_factory: Callable[..., Any],
    *,
    kind: str,
    state: _MCPTelemetryState,
) -> Callable[..., Any]:
    def patched_factory(self: Any, *factory_args: Any, **factory_kwargs: Any) -> Any:
        original_decorator = original_decorator_factory(self, *factory_args, **factory_kwargs)

        def patched_decorator(func: _F) -> _F:
            async def timed_func(*args: Any, **kwargs: Any) -> Any:
                name = _name_from_args(args, kwargs) or getattr(func, "__name__", None)
                start = time.perf_counter()
                success = True
                try:
                    return await func(*args, **kwargs)
                except Exception:
                    success = False
                    raise
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    state.record(
                        kind=f"server_{kind}", name=name, duration_ms=duration_ms, success=success
                    )

            timed_func.__name__ = getattr(func, "__name__", kind)
            timed_func.__doc__ = func.__doc__
            result: _F = original_decorator(timed_func)
            return result

        return patched_decorator

    return patched_factory


class MCPInstrumentor:
    """Instruments `mcp.ClientSession` and `mcp.server.lowlevel.Server`
    to automatically capture tool/resource/prompt call telemetry (name,
    duration, success/failure) — metadata only, never arguments, results,
    resource contents, or prompt contents. See the module docstring for
    why this instrumentor never submits a usage event."""

    def __init__(self) -> None:
        self._state: _MCPTelemetryState | None = None

    def instrument(self) -> None:
        if self._state is not None:
            return
        state = _MCPTelemetryState()

        for method_name in _CLIENT_METHODS_WITH_NAME_ARG:
            original = getattr(ClientSession, method_name)
            state._client_originals[method_name] = original
            setattr(
                ClientSession,
                method_name,
                _wrap_client_method(
                    original, kind=method_name, state=state, enrich_context=True
                ),
            )
        for method_name in _CLIENT_METHODS_WITHOUT_NAME_ARG:
            original = getattr(ClientSession, method_name)
            state._client_originals[method_name] = original
            setattr(
                ClientSession,
                method_name,
                _wrap_client_method(
                    original, kind=method_name, state=state, enrich_context=False
                ),
            )

        for method_name in _SERVER_DECORATOR_METHODS:
            original = getattr(Server, method_name)
            state._server_originals[method_name] = original
            setattr(
                Server,
                method_name,
                _wrap_server_decorator(original, kind=method_name, state=state),
            )

        self._state = state

    def uninstrument(self) -> None:
        if self._state is None:
            return
        for method_name, original in self._state._client_originals.items():
            setattr(ClientSession, method_name, original)
        for method_name, original in self._state._server_originals.items():
            setattr(Server, method_name, original)
        self._state = None

    def is_instrumented(self) -> bool:
        return self._state is not None

    @property
    def events_captured_total(self) -> int:
        if self._state is None:
            return 0
        return self._state.events_captured_total
