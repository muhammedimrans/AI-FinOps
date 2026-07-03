from __future__ import annotations

from typing import Any

import pytest

genai = pytest.importorskip("google.genai")

from google.genai.models import AsyncModels, Models  # noqa: E402
from google.genai.types import (  # noqa: E402
    GenerateContentResponse,
    GenerateContentResponseUsageMetadata,
)

from costorah.instrumentation.google import GeminiInstrumentor  # noqa: E402

_PRISTINE = {
    (Models, "generate_content"): Models.__dict__["generate_content"],
    (Models, "generate_content_stream"): Models.__dict__["generate_content_stream"],
    (AsyncModels, "generate_content"): AsyncModels.__dict__["generate_content"],
    (AsyncModels, "generate_content_stream"): AsyncModels.__dict__["generate_content_stream"],
}


@pytest.fixture(autouse=True)
def _clean_state() -> Any:
    yield
    GeminiInstrumentor().uninstrument()
    for (target, attr), original in _PRISTINE.items():
        setattr(target, attr, original)


def _response(input_tokens: int, output_tokens: int, cached: int | None = None) -> Any:
    return GenerateContentResponse(
        usage_metadata=GenerateContentResponseUsageMetadata(
            prompt_token_count=input_tokens,
            candidates_token_count=output_tokens,
            total_token_count=input_tokens + output_tokens,
            cached_content_token_count=cached,
        )
    )


def test_generate_content_captures_usage(captured_submissions: list[Any]) -> None:
    real = _response(15, 7, cached=3)
    Models.generate_content = lambda self, *a, **k: real

    inst = GeminiInstrumentor()
    inst.instrument()
    resp = Models.generate_content(
        object.__new__(Models), model="gemini-1.5-pro", contents="hi"
    )
    inst.uninstrument()

    assert resp is real
    usage = captured_submissions[0]
    assert usage.provider == "google"
    assert usage.input_tokens == 15
    assert usage.output_tokens == 7
    assert usage.cached_tokens == 3


def test_uninstrument_restores_original() -> None:
    real_original = _PRISTINE[(Models, "generate_content")]
    inst = GeminiInstrumentor()
    inst.instrument()
    assert Models.generate_content is not real_original
    inst.uninstrument()
    assert Models.__dict__["generate_content"] is real_original


def test_error_path_submits_error_status(captured_submissions: list[Any]) -> None:
    def raise_error(self: Any, *a: Any, **k: Any) -> Any:
        raise RuntimeError("down")

    Models.generate_content = raise_error
    inst = GeminiInstrumentor()
    inst.instrument()
    with pytest.raises(RuntimeError):
        Models.generate_content(object.__new__(Models), model="gemini-1.5-pro", contents="hi")
    inst.uninstrument()

    assert captured_submissions[0].status == "error"


def test_generate_content_stream_aggregates_final_chunk(captured_submissions: list[Any]) -> None:
    def fake_stream(self: Any, *a: Any, **k: Any) -> Any:
        return iter([_response(5, 0), _response(5, 3)])

    Models.generate_content_stream = fake_stream
    inst = GeminiInstrumentor()
    inst.instrument()
    stream = Models.generate_content_stream(
        object.__new__(Models), model="gemini-1.5-flash", contents="hi"
    )
    chunks = list(stream)
    inst.uninstrument()

    assert len(chunks) == 2
    assert len(captured_submissions) == 1
    assert captured_submissions[0].input_tokens == 5
    assert captured_submissions[0].output_tokens == 3


async def test_async_generate_content(captured_submissions: list[Any]) -> None:
    real = _response(2, 1)

    async def fake_generate(self: Any, *a: Any, **k: Any) -> Any:
        return real

    AsyncModels.generate_content = fake_generate
    inst = GeminiInstrumentor()
    inst.instrument()
    resp = await AsyncModels.generate_content(
        object.__new__(AsyncModels), model="gemini-2.0-flash", contents="hi"
    )
    inst.uninstrument()

    assert resp is real
    assert captured_submissions[0].input_tokens == 2


def test_normalize_unknown_model_reports_zero_cost() -> None:
    inst = GeminiInstrumentor()
    usage = inst.normalize(
        {"input_tokens": 100, "output_tokens": 50},
        model="gemini-future-model",
        latency_ms=1,
        status="success",
    )
    assert usage.cost == 0.0
    assert usage.metadata["cost_estimated"] is False
