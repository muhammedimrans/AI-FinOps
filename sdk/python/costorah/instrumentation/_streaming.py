"""
Shared streaming-aggregation helpers.

Per the ticket: "Support streamed responses. Only send telemetry after
the stream completes. Collect final token counts, latency, status."
Every provider instrumentor that supports streaming wraps the returned
iterator/async-iterator with these helpers rather than reimplementing
chunk-buffering logic per provider.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator
from typing import Any, Callable, TypeVar

T = TypeVar("T")

OnCompleteSync = Callable[[list[T], int, Exception | None], None]
OnCompleteAsync = Callable[[list[T], int, Exception | None], Any]


class InstrumentedSyncStream(Iterator[T]):
    """Wraps a synchronous provider stream. Buffers nothing beyond the
    chunks needed for the on_complete callback's own aggregation — chunks
    are yielded through untouched, immediately, so streaming latency to
    the caller is unaffected."""

    def __init__(self, inner: Iterator[T], start: float, on_complete: OnCompleteSync[T]) -> None:
        self._inner = inner
        self._start = start
        self._on_complete = on_complete
        self._chunks: list[T] = []
        self._finished = False

    def __iter__(self) -> InstrumentedSyncStream[T]:
        return self

    def __next__(self) -> T:
        try:
            chunk = next(self._inner)
        except StopIteration:
            self._finish(None)
            raise
        except Exception as exc:
            self._finish(exc)
            raise
        self._chunks.append(chunk)
        return chunk

    def _finish(self, error: Exception | None) -> None:
        if self._finished:
            return
        self._finished = True
        elapsed_ms = int((time.perf_counter() - self._start) * 1000)
        self._on_complete(self._chunks, elapsed_ms, error)


class InstrumentedAsyncStream(AsyncIterator[T]):
    """Async counterpart of InstrumentedSyncStream."""

    def __init__(
        self, inner: AsyncIterator[T], start: float, on_complete: OnCompleteAsync[T]
    ) -> None:
        self._inner = inner
        self._start = start
        self._on_complete = on_complete
        self._chunks: list[T] = []
        self._finished = False

    def __aiter__(self) -> InstrumentedAsyncStream[T]:
        return self

    async def __anext__(self) -> T:
        try:
            chunk = await self._inner.__anext__()
        except StopAsyncIteration:
            await self._finish(None)
            raise
        except Exception as exc:
            await self._finish(exc)
            raise
        self._chunks.append(chunk)
        return chunk

    async def _finish(self, error: Exception | None) -> None:
        if self._finished:
            return
        self._finished = True
        elapsed_ms = int((time.perf_counter() - self._start) * 1000)
        result = self._on_complete(self._chunks, elapsed_ms, error)
        if hasattr(result, "__await__"):
            await result
