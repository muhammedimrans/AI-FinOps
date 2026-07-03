"""
BedrockInstrumentor — automatic usage capture for Amazon Bedrock's unified
Converse API (`converse`/`converse_stream`), reached through the official
`boto3` package.

    import boto3
    from costorah.instrumentation import BedrockInstrumentor

    BedrockInstrumentor().instrument()

    client = boto3.client("bedrock-runtime")
    client.converse(modelId="anthropic.claude-3-sonnet...", messages=[...])

Scope note: boto3 service clients are generated dynamically per instance
(there is no fixed `BedrockRuntimeClient` class to patch once at import
time the way every other provider instrumentor patches a stable SDK
class) — see `_apply_patches()`'s docstring for how this instrumentor
works around that using only `boto3.session.Session.client`, boto3's own
public, documented client-creation entry point.

Only the Converse API is instrumented, not the older `invoke_model` — the
Converse API returns a standardized `usage` dict regardless of the
underlying model provider (Anthropic, Titan, Llama, Mistral, ...);
`invoke_model`'s response body is raw, per-model-family JSON that would
require a separate parser per model family to normalize honestly, which
is out of scope for this phase. See docs/TROUBLESHOOTING_INSTRUMENTATION.md.
"""

from __future__ import annotations

import functools
import time
import weakref
from typing import Any

from costorah._logging import get_logger
from costorah._util import generate_request_id
from costorah.instrumentation._submission import submit
from costorah.instrumentation.base import BaseInstrumentor, ExtractedUsage, InstrumentationError
from costorah.instrumentation.pricing import calculate_cost
from costorah.types import UsageStatus

_log = get_logger(__name__)


def _extract(response: Any) -> dict[str, Any]:
    usage = response.get("usage") if isinstance(response, dict) else None
    if not usage:
        return {}
    return {
        "input_tokens": usage.get("inputTokens", 0) or 0,
        "output_tokens": usage.get("outputTokens", 0) or 0,
        "total_tokens": usage.get("totalTokens"),
    }


class BedrockInstrumentor(BaseInstrumentor):
    name = "bedrock"

    def extract_usage(self, response: Any) -> dict[str, Any]:
        return _extract(response)

    def normalize(
        self,
        raw_usage: dict[str, Any],
        *,
        model: str,
        latency_ms: int,
        status: UsageStatus,
        request_id: str | None = None,
    ) -> ExtractedUsage:
        input_tokens = int(raw_usage.get("input_tokens", 0) or 0)
        output_tokens = int(raw_usage.get("output_tokens", 0) or 0)
        cost, estimated = (
            calculate_cost("bedrock", model, input_tokens, output_tokens)
            if self.calculate_cost_enabled
            else (0.0, False)
        )
        metadata: dict[str, Any] = {}
        if self.capture_metadata:
            metadata["cost_estimated"] = estimated
        return ExtractedUsage(
            provider="bedrock",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=raw_usage.get("total_tokens"),
            cost=cost,
            latency_ms=latency_ms,
            status=status,
            request_id=request_id or generate_request_id(),
            metadata=metadata,
        )

    def _apply_patches(self) -> None:
        """boto3 clients are generated per-instance (no stable class to
        patch once — see module docstring), so instead this patches
        `boto3.session.Session.client` (the single public method every
        client-creation path, including the `boto3.client()` module
        function, ultimately calls) to wrap `converse`/`converse_stream`
        on the returned instance whenever `service_name ==
        "bedrock-runtime"`. Existing clients created before instrument()
        was called are not retroactively wrapped — the same limitation
        every provider instrumentor has for objects constructed before
        instrument() runs."""
        try:
            import boto3.session
        except ImportError as exc:
            raise InstrumentationError(
                "The 'boto3' package is not installed. Install it with "
                "`pip install boto3` to use this instrumentor."
            ) from exc

        self._wrapped_client_refs: list[weakref.ReferenceType[Any]] = []
        self._patch(
            boto3.session.Session,
            "client",
            self._make_session_client_wrapper(boto3.session.Session.__dict__["client"]),
        )

    def _make_session_client_wrapper(self, original: Any) -> Any:
        instrumentor = self

        @functools.wraps(original)
        def wrapper(self_session: Any, service_name: str, *args: Any, **kwargs: Any) -> Any:
            client = original(self_session, service_name, *args, **kwargs)
            if service_name == "bedrock-runtime":
                instrumentor._wrap_bedrock_client(client)
            return client

        return wrapper

    def _wrap_bedrock_client(self, client: Any) -> None:
        instrumentor = self
        if not hasattr(client, "converse"):
            return

        real_converse = client.converse
        real_converse_stream = getattr(client, "converse_stream", None)

        def submit_result(model: str, raw: dict[str, Any], elapsed_ms: int, status: str) -> None:
            usage = instrumentor.normalize(
                raw,
                model=model,
                latency_ms=elapsed_ms,
                status=status,  # type: ignore[arg-type]
            )
            instrumentor._record_captured()
            submit(usage, client=instrumentor._client)

        @functools.wraps(real_converse)
        def converse_wrapper(*args: Any, **kwargs: Any) -> Any:
            model = kwargs.get("modelId", "unknown")
            start = time.perf_counter()
            try:
                result = real_converse(*args, **kwargs)
            except Exception:
                submit_result(model, {}, instrumentor._elapsed_ms(start), "error")
                raise
            submit_result(model, _extract(result), instrumentor._elapsed_ms(start), "success")
            return result

        client.converse = converse_wrapper

        if real_converse_stream is not None:

            @functools.wraps(real_converse_stream)
            def converse_stream_wrapper(*args: Any, **kwargs: Any) -> Any:
                model = kwargs.get("modelId", "unknown")
                start = time.perf_counter()
                try:
                    result = real_converse_stream(*args, **kwargs)
                except Exception:
                    submit_result(model, {}, instrumentor._elapsed_ms(start), "error")
                    raise
                # The Converse Stream API's EventStream yields
                # {"metadata": {"usage": {...}}} as its final event —
                # collect it without buffering the whole body, since
                # response text isn't ours to hold onto (see PRIVACY.md).
                return _wrap_converse_event_stream(result, model, start, submit_result)

            client.converse_stream = converse_stream_wrapper

        self._wrapped_client_refs.append(weakref.ref(client))

    def uninstrument(self) -> None:
        """In addition to restoring `Session.client`, unwrap any
        already-created Bedrock client instances this instrumentor
        directly modified (best-effort — a client garbage-collected
        already is simply skipped)."""
        with self._lock:
            if not self._patches:
                return
            for record in reversed(self._patches):
                setattr(record.target, record.attr, record.original)
            self._patches.clear()
            for ref in getattr(self, "_wrapped_client_refs", []):
                client = ref()
                if client is None:
                    continue
                if hasattr(client, "converse"):
                    del client.converse
                if hasattr(client, "converse_stream"):
                    del client.converse_stream
            self._wrapped_client_refs = []
            _log.info("instrumentation_disabled_restored provider=%s", self.name)


def _wrap_converse_event_stream(stream: Any, model: str, start: float, submit_result: Any) -> Any:
    def generator() -> Any:
        raw: dict[str, Any] = {}
        error: Exception | None = None
        try:
            for event in stream:
                metadata = event.get("metadata") if isinstance(event, dict) else None
                if metadata:
                    raw = _extract(metadata)
                yield event
        except Exception as exc:
            error = exc
            raise
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            submit_result(model, raw, elapsed_ms, "error" if error else "success")

    return generator()
