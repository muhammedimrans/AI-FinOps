"""
CohereInstrumentor — automatic usage capture for the official `cohere`
Python package's `ClientV2.chat`/`chat_stream` (and the async
`AsyncClientV2` equivalents).

    import cohere
    from costorah.instrumentation import CohereInstrumentor

    CohereInstrumentor().instrument()

    client = cohere.ClientV2(api_key="...")
    client.chat(model="command-r-plus", messages=[...])
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
    tokens = getattr(usage, "tokens", None) if usage else None
    if tokens is None:
        return {}
    return {
        "input_tokens": getattr(tokens, "input_tokens", 0) or 0,
        "output_tokens": getattr(tokens, "output_tokens", 0) or 0,
    }


def _aggregate_stream(events: list[Any]) -> dict[str, Any]:
    # The terminal "message-end" event carries the final usage/response.
    for event in reversed(events):
        response = getattr(event, "response", None)
        raw = _extract(response) if response is not None else _extract(event)
        if raw:
            return raw
    return {}


class CohereInstrumentor(BaseInstrumentor):
    name = "cohere"

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
            calculate_cost("cohere", model, input_tokens, output_tokens)
            if self.calculate_cost_enabled
            else (0.0, False)
        )
        metadata: dict[str, Any] = {}
        if self.capture_metadata:
            metadata["cost_estimated"] = estimated
        return ExtractedUsage(
            provider="cohere",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_ms=latency_ms,
            status=status,
            request_id=request_id or generate_request_id(),
            metadata=metadata,
        )

    def _apply_patches(self) -> None:
        try:
            from cohere import AsyncClientV2, ClientV2
        except ImportError as exc:
            raise InstrumentationError(
                "The 'cohere' package is not installed. Install it with "
                "`pip install cohere` to use this instrumentor."
            ) from exc

        # `chat`/`chat_stream` are defined on a base class (V2Client), not
        # directly on ClientV2/AsyncClientV2 — use getattr() (MRO-aware)
        # rather than __dict__ to find the real original, matching what
        # BaseInstrumentor._patch() already does internally when recording
        # the patch to restore.
        self._patch(ClientV2, "chat", self._make_wrapper(ClientV2.chat, "sync"))
        self._patch(AsyncClientV2, "chat", self._make_wrapper(AsyncClientV2.chat, "async"))
        self._patch(
            ClientV2,
            "chat_stream",
            self._make_wrapper(ClientV2.chat_stream, "sync_stream"),
        )
        self._patch(
            AsyncClientV2,
            "chat_stream",
            self._make_wrapper(AsyncClientV2.chat_stream, "async_stream"),
        )

    def _make_wrapper(self, original: Any, mode: str) -> Any:
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

        if mode == "async":

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

        if mode == "sync_stream":

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

        if mode == "async_stream":

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
