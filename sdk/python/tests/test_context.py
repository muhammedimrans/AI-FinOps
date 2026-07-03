from __future__ import annotations

import asyncio

from costorah.context import get_request_context, request_context


def test_get_request_context_default_none() -> None:
    assert get_request_context() is None


def test_request_context_sets_and_resets() -> None:
    assert get_request_context() is None
    with request_context(request_id="r1", path="/x"):
        assert get_request_context() == {"request_id": "r1", "path": "/x"}
    assert get_request_context() is None


def test_request_context_nesting_restores_outer() -> None:
    with request_context(a=1):
        assert get_request_context() == {"a": 1}
        with request_context(b=2):
            assert get_request_context() == {"b": 2}
        assert get_request_context() == {"a": 1}


def test_request_context_isolated_across_concurrent_async_tasks() -> None:
    results: dict[str, dict[str, object] | None] = {}

    async def handler(name: str) -> None:
        with request_context(request_id=name):
            await asyncio.sleep(0.01)
            results[name] = get_request_context()

    async def run() -> None:
        await asyncio.gather(handler("a"), handler("b"), handler("c"))

    asyncio.run(run())

    assert results == {
        "a": {"request_id": "a"},
        "b": {"request_id": "b"},
        "c": {"request_id": "c"},
    }
