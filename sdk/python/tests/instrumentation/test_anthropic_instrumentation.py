from __future__ import annotations

from typing import Any

import pytest

anthropic = pytest.importorskip("anthropic")

from anthropic import Anthropic, AsyncAnthropic  # noqa: E402
from anthropic.resources.messages import AsyncMessages, Messages  # noqa: E402
from anthropic.types.message import Message  # noqa: E402
from anthropic.types.text_block import TextBlock  # noqa: E402
from anthropic.types.usage import Usage  # noqa: E402

from costorah.instrumentation.anthropic import AnthropicInstrumentor  # noqa: E402

_PRISTINE = {
    (Messages, "create"): Messages.__dict__["create"],
    (AsyncMessages, "create"): AsyncMessages.__dict__["create"],
}


@pytest.fixture(autouse=True)
def _clean_state() -> Any:
    yield
    AnthropicInstrumentor().uninstrument()
    for (target, attr), original in _PRISTINE.items():
        setattr(target, attr, original)


def _message(
    model: str, input_tokens: int, output_tokens: int, cached: int | None = None
) -> Message:
    return Message(
        id="msg_1",
        type="message",
        role="assistant",
        model=model,
        content=[TextBlock(type="text", text="hi")],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cached,
        ),
    )


def test_sync_create_captures_usage(captured_submissions: list[Any]) -> None:
    real = _message("claude-sonnet-4", 12, 6, cached=2)
    Messages.create = lambda self, *a, **k: real

    inst = AnthropicInstrumentor()
    inst.instrument()
    client = Anthropic(api_key="sk-test")
    resp = client.messages.create(model="claude-sonnet-4", max_tokens=100, messages=[])
    inst.uninstrument()

    assert resp is real
    usage = captured_submissions[0]
    assert usage.provider == "anthropic"
    assert usage.input_tokens == 12
    assert usage.output_tokens == 6
    assert usage.cached_tokens == 2


def test_uninstrument_restores_original() -> None:
    real_original = _PRISTINE[(Messages, "create")]
    inst = AnthropicInstrumentor()
    inst.instrument()
    assert Messages.create is not real_original
    inst.uninstrument()
    assert Messages.__dict__["create"] is real_original


def test_error_path_submits_error_status(captured_submissions: list[Any]) -> None:
    def raise_error(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("down")

    Messages.create = raise_error
    inst = AnthropicInstrumentor()
    inst.instrument()
    client = Anthropic(api_key="sk-test")
    with pytest.raises(RuntimeError):
        client.messages.create(model="claude-sonnet-4", max_tokens=100, messages=[])
    inst.uninstrument()

    assert captured_submissions[0].status == "error"


def test_streaming_aggregates_final_usage(captured_submissions: list[Any]) -> None:
    class FakeEvent:
        def __init__(self, usage: Usage | None) -> None:
            self.usage = usage

    def fake_create(self: Any, *a: Any, **k: Any) -> Any:
        return iter(
            [
                FakeEvent(Usage(input_tokens=10, output_tokens=0)),
                FakeEvent(Usage(input_tokens=10, output_tokens=5)),
            ]
        )

    Messages.create = fake_create
    inst = AnthropicInstrumentor()
    inst.instrument()
    client = Anthropic(api_key="sk-test")
    stream = client.messages.create(
        model="claude-sonnet-4", max_tokens=100, messages=[], stream=True
    )
    events = list(stream)
    inst.uninstrument()

    assert len(events) == 2
    assert len(captured_submissions) == 1
    assert captured_submissions[0].input_tokens == 10
    assert captured_submissions[0].output_tokens == 5


async def test_async_create(captured_submissions: list[Any]) -> None:
    real = _message("claude-sonnet-4", 4, 2)

    async def fake_create(self: Any, *a: Any, **k: Any) -> Any:
        return real

    AsyncMessages.create = fake_create
    inst = AnthropicInstrumentor()
    inst.instrument()
    client = AsyncAnthropic(api_key="sk-test")
    resp = await client.messages.create(model="claude-sonnet-4", max_tokens=100, messages=[])
    inst.uninstrument()

    assert resp is real
    assert captured_submissions[0].input_tokens == 4


def test_normalize_unknown_model_reports_zero_cost() -> None:
    inst = AnthropicInstrumentor()
    usage = inst.normalize(
        {"input_tokens": 100, "output_tokens": 50},
        model="claude-future-model",
        latency_ms=1,
        status="success",
    )
    assert usage.cost == 0.0
    assert usage.metadata["cost_estimated"] is False
