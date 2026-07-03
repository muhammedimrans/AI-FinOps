from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest

from costorah.instrumentation._streaming import InstrumentedAsyncStream, InstrumentedSyncStream


def test_sync_stream_yields_chunks_untouched() -> None:
    calls: list[tuple[list[int], int, Exception | None]] = []

    def on_complete(chunks: list[int], elapsed_ms: int, error: Exception | None) -> None:
        calls.append((chunks, elapsed_ms, error))

    stream = InstrumentedSyncStream(iter([1, 2, 3]), 0.0, on_complete)
    assert list(stream) == [1, 2, 3]
    assert len(calls) == 1
    assert calls[0][0] == [1, 2, 3]
    assert calls[0][2] is None


def test_sync_stream_calls_on_complete_exactly_once() -> None:
    calls: list[int] = []

    def on_complete(chunks: list[int], elapsed_ms: int, error: Exception | None) -> None:
        calls.append(1)

    stream = InstrumentedSyncStream(iter([1]), 0.0, on_complete)
    list(stream)
    # Exhaust again (StopIteration repeatedly) — on_complete must not re-fire.
    with pytest.raises(StopIteration):
        next(stream)
    assert len(calls) == 1


def test_sync_stream_propagates_error_and_reports_it() -> None:
    calls: list[Exception | None] = []

    def failing() -> Iterator[int]:
        yield 1
        raise RuntimeError("boom")

    def on_complete(chunks: list[int], elapsed_ms: int, error: Exception | None) -> None:
        calls.append(error)

    stream = InstrumentedSyncStream(iter(failing()), 0.0, on_complete)
    with pytest.raises(RuntimeError):
        list(stream)
    assert len(calls) == 1
    assert isinstance(calls[0], RuntimeError)


async def test_async_stream_yields_chunks_untouched() -> None:
    calls: list[list[int]] = []

    async def gen() -> AsyncIterator[int]:
        yield 1
        yield 2

    def on_complete(chunks: list[int], elapsed_ms: int, error: Exception | None) -> None:
        calls.append(chunks)

    stream = InstrumentedAsyncStream(gen().__aiter__(), 0.0, on_complete)
    result = [item async for item in stream]
    assert result == [1, 2]
    assert calls == [[1, 2]]


async def test_async_stream_propagates_error() -> None:
    calls: list[Exception | None] = []

    async def failing() -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("boom")

    def on_complete(chunks: list[int], elapsed_ms: int, error: Exception | None) -> None:
        calls.append(error)

    stream = InstrumentedAsyncStream(failing().__aiter__(), 0.0, on_complete)
    with pytest.raises(RuntimeError):
        async for _ in stream:
            pass
    assert isinstance(calls[0], RuntimeError)


async def test_async_stream_on_complete_supports_coroutine() -> None:
    calls: list[list[int]] = []

    async def gen() -> AsyncIterator[int]:
        yield 1

    async def async_on_complete(
        chunks: list[int], elapsed_ms: int, error: Exception | None
    ) -> None:
        calls.append(chunks)

    stream = InstrumentedAsyncStream(gen().__aiter__(), 0.0, async_on_complete)
    async for _ in stream:
        pass
    assert calls == [[1]]
