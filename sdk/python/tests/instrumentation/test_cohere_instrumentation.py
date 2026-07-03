from __future__ import annotations

from typing import Any

import pytest

cohere = pytest.importorskip("cohere")

from cohere import AsyncClientV2, ClientV2  # noqa: E402
from cohere.types.usage import Usage  # noqa: E402
from cohere.types.usage_tokens import UsageTokens  # noqa: E402
from cohere.v2.client import V2Client  # noqa: E402
from cohere.v2.types.v2chat_response import V2ChatResponse  # noqa: E402

from costorah.instrumentation.cohere import CohereInstrumentor  # noqa: E402

_PRISTINE = {
    (ClientV2, "chat"): V2Client.chat,
    (AsyncClientV2, "chat"): AsyncClientV2.chat,
    (ClientV2, "chat_stream"): V2Client.chat_stream,
    (AsyncClientV2, "chat_stream"): AsyncClientV2.chat_stream,
}


@pytest.fixture(autouse=True)
def _clean_state() -> Any:
    yield
    CohereInstrumentor().uninstrument()
    for (target, attr), original in _PRISTINE.items():
        setattr(target, attr, original)


def _response(input_tokens: int, output_tokens: int) -> V2ChatResponse:
    return V2ChatResponse(
        id="c1",
        finish_reason="COMPLETE",
        message={"role": "assistant", "content": []},
        usage=Usage(tokens=UsageTokens(input_tokens=input_tokens, output_tokens=output_tokens)),
    )


def test_chat_captures_usage(captured_submissions: list[Any]) -> None:
    real = _response(6, 3)
    ClientV2.chat = lambda self, *a, **k: real

    inst = CohereInstrumentor()
    inst.instrument()
    resp = ClientV2.chat(object.__new__(ClientV2), model="command-r-plus", messages=[])
    inst.uninstrument()

    assert resp is real
    usage = captured_submissions[0]
    assert usage.provider == "cohere"
    assert usage.input_tokens == 6
    assert usage.output_tokens == 3


def test_uninstrument_restores_original() -> None:
    real_original = _PRISTINE[(ClientV2, "chat")]
    inst = CohereInstrumentor()
    inst.instrument()
    assert ClientV2.chat is not real_original
    inst.uninstrument()
    assert ClientV2.chat is real_original


def test_error_path_submits_error_status(captured_submissions: list[Any]) -> None:
    def raise_error(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("down")

    ClientV2.chat = raise_error
    inst = CohereInstrumentor()
    inst.instrument()
    with pytest.raises(RuntimeError):
        ClientV2.chat(object.__new__(ClientV2), model="command-r-plus", messages=[])
    inst.uninstrument()

    assert captured_submissions[0].status == "error"


def test_chat_stream_aggregates_final_usage(captured_submissions: list[Any]) -> None:
    class FakeEvent:
        def __init__(self, response: Any) -> None:
            self.response = response

    def fake_stream(self: Any, *a: Any, **k: Any) -> Any:
        return iter([FakeEvent(None), FakeEvent(_response(4, 2))])

    ClientV2.chat_stream = fake_stream
    inst = CohereInstrumentor()
    inst.instrument()
    stream = ClientV2.chat_stream(object.__new__(ClientV2), model="command-r", messages=[])
    events = list(stream)
    inst.uninstrument()

    assert len(events) == 2
    assert len(captured_submissions) == 1
    assert captured_submissions[0].input_tokens == 4
    assert captured_submissions[0].output_tokens == 2


async def test_async_chat(captured_submissions: list[Any]) -> None:
    real = _response(1, 1)

    async def fake_chat(self: Any, *a: Any, **k: Any) -> Any:
        return real

    AsyncClientV2.chat = fake_chat
    inst = CohereInstrumentor()
    inst.instrument()
    resp = await AsyncClientV2.chat(
        object.__new__(AsyncClientV2), model="command-r-plus", messages=[]
    )
    inst.uninstrument()

    assert resp is real
    assert captured_submissions[0].input_tokens == 1


def test_normalize_unknown_model_reports_zero_cost() -> None:
    inst = CohereInstrumentor()
    usage = inst.normalize(
        {"input_tokens": 100, "output_tokens": 50},
        model="command-future-model",
        latency_ms=1,
        status="success",
    )
    assert usage.cost == 0.0
    assert usage.metadata["cost_estimated"] is False
