from __future__ import annotations

from typing import Any

import pytest

openai = pytest.importorskip("openai")

from openai import AsyncOpenAI, OpenAI  # noqa: E402
from openai.resources.chat.completions import AsyncCompletions, Completions  # noqa: E402
from openai.resources.responses.responses import AsyncResponses, Responses  # noqa: E402
from openai.types.chat.chat_completion import ChatCompletion  # noqa: E402
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk  # noqa: E402
from openai.types.completion_usage import CompletionUsage  # noqa: E402
from openai.types.responses.response import Response  # noqa: E402
from openai.types.responses.response_usage import (  # noqa: E402
    InputTokensDetails,
    OutputTokensDetails,
    ResponseUsage,
)

from costorah.instrumentation.openai import OpenAIInstrumentor  # noqa: E402

# Pristine originals, captured once before any test instruments anything —
# used to restore exact SDK state after each test, since tests replace
# Completions.create etc. with fakes *before* instrument() so the shared
# patch wraps a network-free fake rather than the real HTTP-calling method.
_PRISTINE = {
    (Completions, "create"): Completions.__dict__["create"],
    (AsyncCompletions, "create"): AsyncCompletions.__dict__["create"],
    (Responses, "create"): Responses.__dict__["create"],
    (AsyncResponses, "create"): AsyncResponses.__dict__["create"],
}


@pytest.fixture(autouse=True)
def _clean_openai_patch_state() -> Any:
    yield
    OpenAIInstrumentor().uninstrument()  # no-op if nothing this instance patched
    for (target, attr), original in _PRISTINE.items():
        setattr(target, attr, original)


def _chat_completion(model: str, prompt_tokens: int, completion_tokens: int) -> ChatCompletion:
    return ChatCompletion(
        id="c1",
        object="chat.completion",
        created=0,
        model=model,
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }
        ],
        usage=CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def _response(model: str, input_tokens: int, output_tokens: int, cached: int = 0) -> Response:
    return Response(
        id="r1",
        created_at=0,
        model=model,
        object="response",
        output=[],
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        instructions=None,
        usage=ResponseUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_tokens_details=InputTokensDetails(cached_tokens=cached),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        ),
    )


def test_instrument_patches_chat_completions_create(captured_submissions: list[Any]) -> None:
    real = _chat_completion("gpt-4o", 10, 5)
    Completions.create = lambda self, *a, **k: real

    inst = OpenAIInstrumentor()
    inst.instrument()
    assert inst.is_instrumented()

    client = OpenAI(api_key="sk-test")
    resp = client.chat.completions.create(model="gpt-4o", messages=[])
    inst.uninstrument()
    assert resp is real
    assert len(captured_submissions) == 1
    usage = captured_submissions[0]
    assert usage.provider == "openai"
    assert usage.input_tokens == 10
    assert usage.output_tokens == 5
    assert usage.status == "success"


def test_uninstrument_restores_original_create() -> None:
    real_original = _PRISTINE[(Completions, "create")]
    inst = OpenAIInstrumentor()
    inst.instrument()
    assert Completions.create is not real_original
    inst.uninstrument()
    assert Completions.__dict__["create"] is real_original


def test_responses_api_success_criterion_path(captured_submissions: list[Any]) -> None:
    """The ticket's literal success criterion:
    `client.responses.create(model="gpt-4.1", input="Hello")`."""
    real = _response("gpt-4.1", 20, 8, cached=3)
    Responses.create = lambda self, *a, **k: real

    inst = OpenAIInstrumentor()
    inst.instrument()

    client = OpenAI(api_key="sk-test")
    resp = client.responses.create(model="gpt-4.1", input="Hello")
    inst.uninstrument()
    assert resp is real
    usage = captured_submissions[0]
    assert usage.provider == "openai"
    assert usage.model == "gpt-4.1"
    assert usage.input_tokens == 20
    assert usage.output_tokens == 8
    assert usage.cached_tokens == 3


def test_error_path_still_submits_telemetry(captured_submissions: list[Any]) -> None:
    def raise_error(self: Any, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("provider down")

    Completions.create = raise_error

    inst = OpenAIInstrumentor()
    inst.instrument()

    client = OpenAI(api_key="sk-test")
    with pytest.raises(RuntimeError):
        client.chat.completions.create(model="gpt-4o", messages=[])
    inst.uninstrument()

    usage = captured_submissions[0]
    assert usage.status == "error"
    assert usage.input_tokens == 0


def test_streaming_only_submits_after_completion(captured_submissions: list[Any]) -> None:
    def make_chunk(usage: CompletionUsage | None = None) -> ChatCompletionChunk:
        return ChatCompletionChunk(
            id="c1",
            object="chat.completion.chunk",
            created=0,
            model="gpt-4o",
            choices=[{"index": 0, "delta": {"content": "hi"}, "finish_reason": None}],
            usage=usage,
        )

    def fake_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        def gen() -> Any:
            yield make_chunk()
            yield make_chunk(
                CompletionUsage(prompt_tokens=4, completion_tokens=2, total_tokens=6)
            )

        return gen()

    Completions.create = fake_create

    inst = OpenAIInstrumentor()
    inst.instrument()
    client = OpenAI(api_key="sk-test")
    stream = client.chat.completions.create(model="gpt-4o", messages=[], stream=True)

    chunks = []
    for chunk in stream:
        chunks.append(chunk)
        assert captured_submissions == []  # nothing submitted mid-stream
    inst.uninstrument()

    assert len(chunks) == 2
    assert len(captured_submissions) == 1
    assert captured_submissions[0].input_tokens == 4
    assert captured_submissions[0].output_tokens == 2


async def test_async_chat_completion(captured_submissions: list[Any]) -> None:
    real = _chat_completion("gpt-4o", 3, 1)

    async def fake_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        return real

    AsyncCompletions.create = fake_create

    inst = OpenAIInstrumentor()
    inst.instrument()
    client = AsyncOpenAI(api_key="sk-test")
    resp = await client.chat.completions.create(model="gpt-4o", messages=[])
    inst.uninstrument()
    assert resp is real
    assert captured_submissions[0].input_tokens == 3


async def test_async_responses_api(captured_submissions: list[Any]) -> None:
    real = _response("gpt-4.1", 7, 2)

    async def fake_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        return real

    AsyncResponses.create = fake_create

    inst = OpenAIInstrumentor()
    inst.instrument()
    client = AsyncOpenAI(api_key="sk-test")
    resp = await client.responses.create(model="gpt-4.1", input="hi")
    inst.uninstrument()
    assert resp is real
    assert captured_submissions[0].input_tokens == 7


def test_normalize_marks_cost_estimated_for_known_model() -> None:
    inst = OpenAIInstrumentor()
    usage = inst.normalize(
        {"input_tokens": 1_000_000, "output_tokens": 0},
        model="gpt-4o",
        latency_ms=5,
        status="success",
    )
    assert usage.cost == 2.5
    assert usage.metadata["cost_estimated"] is True


def test_normalize_reports_zero_cost_for_unknown_model() -> None:
    inst = OpenAIInstrumentor()
    usage = inst.normalize(
        {"input_tokens": 100, "output_tokens": 50},
        model="some-future-model",
        latency_ms=5,
        status="success",
    )
    assert usage.cost == 0.0
    assert usage.metadata["cost_estimated"] is False


def test_calculate_cost_disabled_yields_zero() -> None:
    inst = OpenAIInstrumentor(calculate_cost=False)
    usage = inst.normalize(
        {"input_tokens": 1_000_000, "output_tokens": 0},
        model="gpt-4o",
        latency_ms=5,
        status="success",
    )
    assert usage.cost == 0.0


def test_capture_metadata_disabled_omits_cost_estimated_key() -> None:
    inst = OpenAIInstrumentor(capture_metadata=False)
    usage = inst.normalize(
        {"input_tokens": 10, "output_tokens": 5}, model="gpt-4o", latency_ms=5, status="success"
    )
    assert usage.metadata == {}
