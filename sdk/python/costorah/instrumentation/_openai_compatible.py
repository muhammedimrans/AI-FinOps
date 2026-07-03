"""
Shared patch logic for every OpenAI-SDK-compatible provider: OpenAI
itself, Azure OpenAI, and any provider commonly accessed through
`openai.OpenAI(base_url=...)` (OpenRouter, Ollama, xAI/Grok all publish
OpenAI-compatible endpoints and are conventionally used via the official
`openai` Python package rather than a bespoke client).

All five instrumentors (OpenAIInstrumentor, AzureOpenAIInstrumentor,
OpenRouterInstrumentor, OllamaInstrumentor, GrokInstrumentor) patch the
exact same two classes — `openai.resources.chat.completions.Completions`
and `openai.resources.responses.responses.Responses` (plus their async
counterparts) — since that's the single interception point every one of
these providers' traffic passes through in the openai package. To avoid
"No duplicated logic" (per the ticket) and to avoid one instrumentor's
`uninstrument()` undoing another's patch, the actual monkey-patch is
applied once process-wide via a reference count; each instrumentor
instance's own `is_instrumented()` still reflects only its own
instrument()/uninstrument() calls.

Provider identity for a given call is determined at call time by
inspecting the client's `base_url` (or its class name for Azure) — the
same technique real APM SDKs use for OpenAI-compatible endpoints, since
the openai package itself has no per-provider marker.
"""

from __future__ import annotations

import functools
import threading
import time
from typing import Any

from costorah._logging import get_logger
from costorah._util import generate_request_id
from costorah.instrumentation._streaming import InstrumentedAsyncStream, InstrumentedSyncStream
from costorah.instrumentation._submission import submit
from costorah.instrumentation.base import BaseInstrumentor, ExtractedUsage, InstrumentationError
from costorah.instrumentation.pricing import calculate_cost

_log = get_logger(__name__)

_PROVIDER_HOST_HINTS: tuple[tuple[str, str], ...] = (
    ("openrouter.ai", "openrouter"),
    ("localhost:11434", "ollama"),
    ("127.0.0.1:11434", "ollama"),
    ("api.x.ai", "grok"),
)


def _detect_provider(client: Any) -> str:
    class_name = type(client).__name__
    if class_name in ("AzureOpenAI", "AsyncAzureOpenAI"):
        return "azure_openai"
    base_url = str(getattr(client, "base_url", "") or "")
    for hint, provider in _PROVIDER_HOST_HINTS:
        if hint in base_url:
            return provider
    return "openai"


def _extract_chat_usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(prompt_details, "cached_tokens", None) if prompt_details else None
    return {
        "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", None),
        "cached_tokens": cached,
    }


def _extract_responses_usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    input_details = getattr(usage, "input_tokens_details", None)
    cached = getattr(input_details, "cached_tokens", None) if input_details else None
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", None),
        "cached_tokens": cached,
    }


class _OpenAICompatibleInstrumentor(BaseInstrumentor):
    """Base for every OpenAI-SDK-compatible provider instrumentor. Not
    abstract at the Python level (it fully implements BaseInstrumentor),
    but subclasses exist so each provider has its own class name/identity
    per the ticket's `OpenAIInstrumentor()`, `AzureOpenAIInstrumentor()`,
    etc. API."""

    #: Every OpenAI-family instrumentor claims exactly one provider slug.
    #: The shared patch (see below) still runs `_detect_provider()` on
    #: every call to label it correctly, but only submits telemetry for
    #: providers that have an *active, explicitly instrumented* family
    #: member — instrumenting only OpenAIInstrumentor never captures
    #: traffic through an AzureOpenAI client your code also happens to
    #: use, matching how every reference APM SDK scopes "what's on".
    fixed_provider: str = "openai"

    def extract_usage(self, response: Any) -> dict[str, Any]:
        if hasattr(response, "output"):  # Responses API shape
            return _extract_responses_usage(response)
        return _extract_chat_usage(response)  # Chat Completions shape

    def normalize(
        self,
        raw_usage: dict[str, Any],
        *,
        model: str,
        latency_ms: int,
        status: Any,
        request_id: str | None = None,
    ) -> ExtractedUsage:
        provider = self.fixed_provider
        input_tokens = int(raw_usage.get("input_tokens", 0) or 0)
        output_tokens = int(raw_usage.get("output_tokens", 0) or 0)
        cost, estimated = (
            calculate_cost(provider, model, input_tokens, output_tokens)
            if self.calculate_cost_enabled
            else (0.0, False)
        )
        metadata: dict[str, Any] = {}
        if self.capture_metadata:
            metadata["cost_estimated"] = estimated
        return ExtractedUsage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=raw_usage.get("cached_tokens"),
            total_tokens=raw_usage.get("total_tokens"),
            cost=cost,
            latency_ms=latency_ms,
            status=status,
            request_id=request_id or generate_request_id(),
            metadata=metadata,
        )

    def _apply_patches(self) -> None:
        _ensure_openai_patched(self)

    def uninstrument(self) -> None:
        """Overrides BaseInstrumentor.uninstrument(): the shared,
        reference-counted OpenAI-family patch (see `_ensure_openai_patched`)
        must only be physically restored when the *last* family member
        uninstruments — a plain restore-from-self._patches would clobber
        a sibling instrumentor (e.g. AzureOpenAIInstrumentor) still
        relying on the same patched methods."""
        with self._lock:
            if not self._patches:
                return
            release_openai_patch(self)
            self._patches.clear()
            _log.info("instrumentation_disabled_restored provider=%s", self.name)


# ── Process-wide shared patch (multiple family members, one physical patch) ─

_patch_lock = threading.Lock()
_active_instrumentors: list[_OpenAICompatibleInstrumentor] = []


def _submit_for_instrumentors(
    provider: str, model: str, raw_usage: dict[str, Any], latency_ms: int, status: str
) -> None:
    for instrumentor in list(_active_instrumentors):
        if instrumentor.fixed_provider != provider:
            continue
        usage = instrumentor.normalize(raw_usage, model=model, latency_ms=latency_ms, status=status)
        instrumentor._record_captured()
        submit(usage, client=instrumentor._client)


def _make_chat_wrapper(original: Any, *, is_async: bool) -> Any:
    if is_async:

        @functools.wraps(original)
        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            provider = _detect_provider(self._client)
            model = kwargs.get("model", "unknown")
            start = time.perf_counter()
            try:
                result = await original(self, *args, **kwargs)
            except Exception:
                elapsed = int((time.perf_counter() - start) * 1000)
                _submit_for_instrumentors(provider, model, {}, elapsed, "error")
                raise
            if kwargs.get("stream"):
                return _wrap_async_chat_stream(result, provider, model, start)
            elapsed = int((time.perf_counter() - start) * 1000)
            raw = _extract_chat_usage(result)
            _submit_for_instrumentors(provider, model, raw, elapsed, "success")
            return result

        return async_wrapper

    @functools.wraps(original)
    def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        provider = _detect_provider(self._client)
        model = kwargs.get("model", "unknown")
        start = time.perf_counter()
        try:
            result = original(self, *args, **kwargs)
        except Exception:
            elapsed = int((time.perf_counter() - start) * 1000)
            _submit_for_instrumentors(provider, model, {}, elapsed, "error")
            raise
        if kwargs.get("stream"):
            return _wrap_sync_chat_stream(result, provider, model, start)
        elapsed = int((time.perf_counter() - start) * 1000)
        raw = _extract_chat_usage(result)
        _submit_for_instrumentors(provider, model, raw, elapsed, "success")
        return result

    return sync_wrapper


def _make_responses_wrapper(original: Any, *, is_async: bool) -> Any:
    if is_async:

        @functools.wraps(original)
        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            provider = _detect_provider(self._client)
            model = kwargs.get("model", "unknown")
            start = time.perf_counter()
            try:
                result = await original(self, *args, **kwargs)
            except Exception:
                elapsed = int((time.perf_counter() - start) * 1000)
                _submit_for_instrumentors(provider, model, {}, elapsed, "error")
                raise
            elapsed = int((time.perf_counter() - start) * 1000)
            raw = _extract_responses_usage(result)
            _submit_for_instrumentors(provider, model, raw, elapsed, "success")
            return result

        return async_wrapper

    @functools.wraps(original)
    def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        provider = _detect_provider(self._client)
        model = kwargs.get("model", "unknown")
        start = time.perf_counter()
        try:
            result = original(self, *args, **kwargs)
        except Exception:
            elapsed = int((time.perf_counter() - start) * 1000)
            _submit_for_instrumentors(provider, model, {}, elapsed, "error")
            raise
        elapsed = int((time.perf_counter() - start) * 1000)
        raw = _extract_responses_usage(result)
        _submit_for_instrumentors(provider, model, raw, elapsed, "success")
        return result

    return sync_wrapper


def _wrap_sync_chat_stream(stream: Any, provider: str, model: str, start: float) -> Any:
    def on_complete(chunks: list[Any], elapsed_ms: int, error: Exception | None) -> None:
        raw = _aggregate_chat_stream_usage(chunks)
        status = "error" if error else "success"
        _submit_for_instrumentors(provider, model, raw, elapsed_ms, status)

    return InstrumentedSyncStream(iter(stream), start, on_complete)


def _wrap_async_chat_stream(stream: Any, provider: str, model: str, start: float) -> Any:
    def on_complete(chunks: list[Any], elapsed_ms: int, error: Exception | None) -> None:
        raw = _aggregate_chat_stream_usage(chunks)
        status = "error" if error else "success"
        _submit_for_instrumentors(provider, model, raw, elapsed_ms, status)

    return InstrumentedAsyncStream(stream.__aiter__(), start, on_complete)


def _aggregate_chat_stream_usage(chunks: list[Any]) -> dict[str, Any]:
    # OpenAI only includes `usage` on the final chunk when
    # stream_options={"include_usage": True} was requested; if absent,
    # there is nothing to aggregate — we report zero tokens honestly
    # rather than guessing from chunk count.
    for chunk in reversed(chunks):
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            return {
                "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage, "total_tokens", None),
            }
    return {}


# Original (pre-patch) methods, captured once by whichever instrumentor
# applies the shared patch first. Kept module-level (not owned by any one
# instrumentor instance) so restoration on the *last* uninstrument() call
# works correctly regardless of instrumentation/uninstrumentation order
# across OpenAI-family instrumentors.
_originals: dict[tuple[type, str], Any] | None = None


def _ensure_openai_patched(instrumentor: _OpenAICompatibleInstrumentor) -> None:
    global _originals
    with _patch_lock:
        _active_instrumentors.append(instrumentor)
        instrumentor._patches.append(True)  # non-empty marker for is_instrumented()

        if _originals is not None:
            return  # another family member already applied the shared patch

        try:
            from openai.resources.chat.completions import AsyncCompletions, Completions
            from openai.resources.responses.responses import AsyncResponses, Responses
        except ImportError as exc:
            _active_instrumentors.remove(instrumentor)
            instrumentor._patches.clear()
            raise InstrumentationError(
                "The 'openai' package is not installed. Install it with "
                "`pip install openai` to use this instrumentor."
            ) from exc

        _originals = {
            (Completions, "create"): Completions.__dict__["create"],
            (AsyncCompletions, "create"): AsyncCompletions.__dict__["create"],
            (Responses, "create"): Responses.__dict__["create"],
            (AsyncResponses, "create"): AsyncResponses.__dict__["create"],
        }
        # setattr(), not `Completions.create = ...` — mypy treats a method
        # slot on a class object as non-reassignable via plain attribute
        # syntax; setattr() sidesteps that without a type: ignore.
        setattr(  # noqa: B010
            Completions,
            "create",
            _make_chat_wrapper(_originals[Completions, "create"], is_async=False),
        )
        setattr(  # noqa: B010
            AsyncCompletions,
            "create",
            _make_chat_wrapper(_originals[AsyncCompletions, "create"], is_async=True),
        )
        setattr(  # noqa: B010
            Responses,
            "create",
            _make_responses_wrapper(_originals[Responses, "create"], is_async=False),
        )
        setattr(  # noqa: B010
            AsyncResponses,
            "create",
            _make_responses_wrapper(_originals[AsyncResponses, "create"], is_async=True),
        )


def release_openai_patch(instrumentor: _OpenAICompatibleInstrumentor) -> None:
    global _originals
    with _patch_lock:
        if instrumentor in _active_instrumentors:
            _active_instrumentors.remove(instrumentor)
        if _active_instrumentors:
            return  # other family members still instrumented — leave the patch in place
        if _originals is None:
            return
        for (target, attr), original in _originals.items():
            setattr(target, attr, original)
        _originals = None
