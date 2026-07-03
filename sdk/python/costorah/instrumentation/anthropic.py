"""
AnthropicInstrumentor — automatic usage capture for the official
`anthropic` Python package's Messages API (sync, async, and streaming).

    from anthropic import Anthropic
    from costorah.instrumentation import AnthropicInstrumentor

    AnthropicInstrumentor().instrument()

    client = Anthropic()
    client.messages.create(model="claude-sonnet-4", max_tokens=1024, messages=[...])
"""

from __future__ import annotations

import functools
import time
from typing import Any

from costorah._logging import get_logger
from costorah._util import generate_request_id
from costorah.instrumentation._streaming import InstrumentedAsyncStream, InstrumentedSyncStream
from costorah.instrumentation._submission import submit
from costorah.instrumentation.base import BaseInstrumentor, ExtractedUsage, InstrumentationError
from costorah.instrumentation.pricing import calculate_cost
from costorah.types import UsageStatus

_log = get_logger(__name__)


def _extract(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cached_tokens": getattr(usage, "cache_read_input_tokens", None),
    }


def _aggregate_stream(events: list[Any]) -> dict[str, Any]:
    """Anthropic streams `message_start` (input_tokens, output_tokens=0)
    then `message_delta` events whose `usage` carries the running output
    token count — the last event with usage info has the final totals."""
    raw: dict[str, Any] = {}
    for event in events:
        usage = getattr(event, "usage", None) or getattr(
            getattr(event, "message", None), "usage", None
        )
        if usage is None:
            continue
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        if input_tokens is not None:
            raw["input_tokens"] = input_tokens
        if output_tokens is not None:
            raw["output_tokens"] = output_tokens
        cached = getattr(usage, "cache_read_input_tokens", None)
        if cached is not None:
            raw["cached_tokens"] = cached
    return raw


class AnthropicInstrumentor(BaseInstrumentor):
    name = "anthropic"

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
            calculate_cost("anthropic", model, input_tokens, output_tokens)
            if self.calculate_cost_enabled
            else (0.0, False)
        )
        metadata: dict[str, Any] = {}
        if self.capture_metadata:
            metadata["cost_estimated"] = estimated
        return ExtractedUsage(
            provider="anthropic",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=raw_usage.get("cached_tokens"),
            total_tokens=(input_tokens + output_tokens) if raw_usage else None,
            cost=cost,
            latency_ms=latency_ms,
            status=status,
            request_id=request_id or generate_request_id(),
            metadata=metadata,
        )

    def _apply_patches(self) -> None:
        try:
            from anthropic.resources.messages import AsyncMessages, Messages
        except ImportError as exc:
            raise InstrumentationError(
                "The 'anthropic' package is not installed. Install it with "
                "`pip install anthropic` to use this instrumentor."
            ) from exc

        self._patch(Messages, "create", self._make_wrapper(Messages.__dict__["create"], False))
        self._patch(
            AsyncMessages, "create", self._make_wrapper(AsyncMessages.__dict__["create"], True)
        )

    def _make_wrapper(self, original: Any, is_async: bool) -> Any:
        instrumentor = self

        def submit_result(model: str, raw: dict[str, Any], elapsed_ms: int, status: str) -> None:
            usage = instrumentor.normalize(
                raw,
                model=model,
                latency_ms=elapsed_ms,
                status=status,  # type: ignore[arg-type]
            )
            instrumentor._record_captured()
            submit(usage, client=instrumentor._client)

        if is_async:

            @functools.wraps(original)
            async def async_wrapper(self_client: Any, *args: Any, **kwargs: Any) -> Any:
                model = kwargs.get("model", "unknown")
                start = time.perf_counter()
                try:
                    result = await original(self_client, *args, **kwargs)
                except Exception:
                    submit_result(model, {}, instrumentor._elapsed_ms(start), "error")
                    raise
                if kwargs.get("stream"):
                    return _wrap_async_stream(result, model, start, submit_result)
                submit_result(model, _extract(result), instrumentor._elapsed_ms(start), "success")
                return result

            return async_wrapper

        @functools.wraps(original)
        def sync_wrapper(self_client: Any, *args: Any, **kwargs: Any) -> Any:
            model = kwargs.get("model", "unknown")
            start = time.perf_counter()
            try:
                result = original(self_client, *args, **kwargs)
            except Exception:
                submit_result(model, {}, instrumentor._elapsed_ms(start), "error")
                raise
            if kwargs.get("stream"):
                return _wrap_sync_stream(result, model, start, submit_result)
            submit_result(model, _extract(result), instrumentor._elapsed_ms(start), "success")
            return result

        return sync_wrapper


def _wrap_sync_stream(stream: Any, model: str, start: float, submit_result: Any) -> Any:
    def on_complete(chunks: list[Any], elapsed_ms: int, error: Exception | None) -> None:
        raw = _aggregate_stream(chunks)
        submit_result(model, raw, elapsed_ms, "error" if error else "success")

    return InstrumentedSyncStream(iter(stream), start, on_complete)


def _wrap_async_stream(stream: Any, model: str, start: float, submit_result: Any) -> Any:
    def on_complete(chunks: list[Any], elapsed_ms: int, error: Exception | None) -> None:
        raw = _aggregate_stream(chunks)
        submit_result(model, raw, elapsed_ms, "error" if error else "success")

    return InstrumentedAsyncStream(stream.__aiter__(), start, on_complete)
