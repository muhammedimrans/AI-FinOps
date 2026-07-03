from __future__ import annotations

from typing import Any

import pytest

mistralai = pytest.importorskip("mistralai")

from mistralai.chat import Chat  # noqa: E402
from mistralai.models.chatcompletionresponse import ChatCompletionResponse  # noqa: E402
from mistralai.models.completionchunk import CompletionChunk  # noqa: E402
from mistralai.models.completionevent import CompletionEvent  # noqa: E402
from mistralai.models.usageinfo import UsageInfo  # noqa: E402

from costorah.instrumentation.mistral import MistralInstrumentor  # noqa: E402

_PRISTINE = {
    (Chat, "complete"): Chat.__dict__["complete"],
    (Chat, "complete_async"): Chat.__dict__["complete_async"],
    (Chat, "stream"): Chat.__dict__["stream"],
    (Chat, "stream_async"): Chat.__dict__["stream_async"],
}


@pytest.fixture(autouse=True)
def _clean_state() -> Any:
    yield
    MistralInstrumentor().uninstrument()
    for (target, attr), original in _PRISTINE.items():
        setattr(target, attr, original)


def _completion(model: str, input_tokens: int, output_tokens: int) -> ChatCompletionResponse:
    return ChatCompletionResponse(
        id="c1",
        object="chat.completion",
        model=model,
        choices=[],
        created=0,
        usage=UsageInfo(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
    )


def test_complete_captures_usage(captured_submissions: list[Any]) -> None:
    real = _completion("mistral-large-latest", 9, 4)
    Chat.complete = lambda self, *a, **k: real

    inst = MistralInstrumentor()
    inst.instrument()
    resp = Chat.complete(object.__new__(Chat), model="mistral-large-latest", messages=[])
    inst.uninstrument()

    assert resp is real
    usage = captured_submissions[0]
    assert usage.provider == "mistral"
    assert usage.input_tokens == 9
    assert usage.output_tokens == 4


def test_uninstrument_restores_original() -> None:
    real_original = _PRISTINE[(Chat, "complete")]
    inst = MistralInstrumentor()
    inst.instrument()
    assert Chat.complete is not real_original
    inst.uninstrument()
    assert Chat.__dict__["complete"] is real_original


def test_error_path_submits_error_status(captured_submissions: list[Any]) -> None:
    def raise_error(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("down")

    Chat.complete = raise_error
    inst = MistralInstrumentor()
    inst.instrument()
    with pytest.raises(RuntimeError):
        Chat.complete(object.__new__(Chat), model="mistral-large-latest", messages=[])
    inst.uninstrument()

    assert captured_submissions[0].status == "error"


def test_stream_aggregates_final_usage(captured_submissions: list[Any]) -> None:
    def make_event(usage: UsageInfo | None) -> CompletionEvent:
        return CompletionEvent(
            data=CompletionChunk(id="c1", model="mistral-small-latest", choices=[], usage=usage)
        )

    def fake_stream(self: Any, *a: Any, **k: Any) -> Any:
        return iter(
            [
                make_event(None),
                make_event(UsageInfo(prompt_tokens=3, completion_tokens=2, total_tokens=5)),
            ]
        )

    Chat.stream = fake_stream
    inst = MistralInstrumentor()
    inst.instrument()
    stream = Chat.stream(object.__new__(Chat), model="mistral-small-latest", messages=[])
    events = list(stream)
    inst.uninstrument()

    assert len(events) == 2
    assert len(captured_submissions) == 1
    assert captured_submissions[0].input_tokens == 3
    assert captured_submissions[0].output_tokens == 2


async def test_complete_async(captured_submissions: list[Any]) -> None:
    real = _completion("mistral-large-latest", 2, 1)

    async def fake_complete(self: Any, *a: Any, **k: Any) -> Any:
        return real

    Chat.complete_async = fake_complete
    inst = MistralInstrumentor()
    inst.instrument()
    resp = await Chat.complete_async(
        object.__new__(Chat), model="mistral-large-latest", messages=[]
    )
    inst.uninstrument()

    assert resp is real
    assert captured_submissions[0].input_tokens == 2


def test_normalize_unknown_model_reports_zero_cost() -> None:
    inst = MistralInstrumentor()
    usage = inst.normalize(
        {"input_tokens": 100, "output_tokens": 50},
        model="mistral-future-model",
        latency_ms=1,
        status="success",
    )
    assert usage.cost == 0.0
    assert usage.metadata["cost_estimated"] is False
