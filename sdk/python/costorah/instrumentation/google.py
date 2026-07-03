"""
GeminiInstrumentor — automatic usage capture for the official `google-genai`
Python package's `Models.generate_content`/`generate_content_stream` (sync
and async; Google uses a separate method for streaming rather than a
`stream=True` kwarg).

    from google import genai
    from costorah.instrumentation import GeminiInstrumentor

    GeminiInstrumentor().instrument()

    client = genai.Client()
    client.models.generate_content(model="gemini-1.5-pro", contents="Hello")
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
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
        "cached_tokens": getattr(usage, "cached_content_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
    }


def _aggregate_stream(chunks: list[Any]) -> dict[str, Any]:
    # Each chunk's usage_metadata already reflects running totals for the
    # response so far — the last chunk carries the final counts.
    for chunk in reversed(chunks):
        raw = _extract(chunk)
        if raw:
            return raw
    return {}


class GeminiInstrumentor(BaseInstrumentor):
    name = "google"

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
            calculate_cost("google", model, input_tokens, output_tokens)
            if self.calculate_cost_enabled
            else (0.0, False)
        )
        metadata: dict[str, Any] = {}
        if self.capture_metadata:
            metadata["cost_estimated"] = estimated
        return ExtractedUsage(
            provider="google",
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
        try:
            from google.genai.models import AsyncModels, Models
        except ImportError as exc:
            raise InstrumentationError(
                "The 'google-genai' package is not installed. Install it "
                "with `pip install google-genai` to use this instrumentor."
            ) from exc

        self._patch(
            Models,
            "generate_content",
            self._make_wrapper(Models.__dict__["generate_content"], is_async=False, stream=False),
        )
        self._patch(
            Models,
            "generate_content_stream",
            self._make_wrapper(
                Models.__dict__["generate_content_stream"], is_async=False, stream=True
            ),
        )
        self._patch(
            AsyncModels,
            "generate_content",
            self._make_wrapper(
                AsyncModels.__dict__["generate_content"], is_async=True, stream=False
            ),
        )
        self._patch(
            AsyncModels,
            "generate_content_stream",
            self._make_wrapper(
                AsyncModels.__dict__["generate_content_stream"], is_async=True, stream=True
            ),
        )

    def _make_wrapper(self, original: Any, *, is_async: bool, stream: bool) -> Any:
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

        if is_async and not stream:

            @functools.wraps(original)
            async def async_wrapper(self_client: Any, *args: Any, **kwargs: Any) -> Any:
                model = kwargs.get("model", "unknown")
                start = time.perf_counter()
                try:
                    result = await original(self_client, *args, **kwargs)
                except Exception:
                    submit_result(model, {}, instrumentor._elapsed_ms(start), "error")
                    raise
                submit_result(model, _extract(result), instrumentor._elapsed_ms(start), "success")
                return result

            return async_wrapper

        if is_async and stream:

            @functools.wraps(original)
            async def async_stream_wrapper(self_client: Any, *args: Any, **kwargs: Any) -> Any:
                model = kwargs.get("model", "unknown")
                start = time.perf_counter()
                result = await original(self_client, *args, **kwargs)

                def on_complete(
                    chunks: list[Any], elapsed_ms: int, error: Exception | None
                ) -> None:
                    raw = _aggregate_stream(chunks)
                    submit_result(model, raw, elapsed_ms, "error" if error else "success")

                return InstrumentedAsyncStream(result.__aiter__(), start, on_complete)

            return async_stream_wrapper

        if stream:

            @functools.wraps(original)
            def sync_stream_wrapper(self_client: Any, *args: Any, **kwargs: Any) -> Any:
                model = kwargs.get("model", "unknown")
                start = time.perf_counter()
                result = original(self_client, *args, **kwargs)

                def on_complete(
                    chunks: list[Any], elapsed_ms: int, error: Exception | None
                ) -> None:
                    raw = _aggregate_stream(chunks)
                    submit_result(model, raw, elapsed_ms, "error" if error else "success")

                return InstrumentedSyncStream(iter(result), start, on_complete)

            return sync_stream_wrapper

        @functools.wraps(original)
        def sync_wrapper(self_client: Any, *args: Any, **kwargs: Any) -> Any:
            model = kwargs.get("model", "unknown")
            start = time.perf_counter()
            try:
                result = original(self_client, *args, **kwargs)
            except Exception:
                submit_result(model, {}, instrumentor._elapsed_ms(start), "error")
                raise
            submit_result(model, _extract(result), instrumentor._elapsed_ms(start), "success")
            return result

        return sync_wrapper
