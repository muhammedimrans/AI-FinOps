from __future__ import annotations

import threading
from typing import Any

import pytest

openai = pytest.importorskip("openai")

from openai import OpenAI  # noqa: E402
from openai.resources.chat.completions import Completions  # noqa: E402
from openai.types.chat.chat_completion import ChatCompletion  # noqa: E402
from openai.types.completion_usage import CompletionUsage  # noqa: E402

from costorah.instrumentation.openai import OpenAIInstrumentor  # noqa: E402

_PRISTINE_CREATE = Completions.__dict__["create"]


@pytest.fixture(autouse=True)
def _clean_state() -> Any:
    yield
    OpenAIInstrumentor().uninstrument()
    Completions.create = _PRISTINE_CREATE


def test_concurrent_instrumented_calls_from_multiple_threads(
    captured_submissions: list[Any],
) -> None:
    """Many threads calling the same instrumented method concurrently
    must not corrupt or cross-contaminate telemetry — each call's own
    request_id must appear exactly once."""

    def fake_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        model = kwargs["model"]
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
            usage=CompletionUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

    Completions.create = fake_create
    inst = OpenAIInstrumentor()
    inst.instrument()
    client = OpenAI(api_key="sk-test")

    errors: list[Exception] = []

    def worker(index: int) -> None:
        try:
            client.chat.completions.create(model=f"model-{index}", messages=[])
        except Exception as exc:  # pragma: no cover - surfaced via assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    inst.uninstrument()

    assert errors == []
    assert len(captured_submissions) == 50
    models_seen = {u.model for u in captured_submissions}
    assert models_seen == {f"model-{i}" for i in range(50)}
    assert inst.events_captured_total == 50


def test_concurrent_instrument_and_uninstrument_from_multiple_instrumentors(
    captured_submissions: list[Any],
) -> None:
    """Multiple OpenAI-family instrumentors instrumenting/uninstrumenting
    concurrently must never leave the shared patch in a half-applied
    state (see _openai_compatible.py's reference-counted design)."""
    from costorah.instrumentation.grok import GrokInstrumentor
    from costorah.instrumentation.ollama import OllamaInstrumentor
    from costorah.instrumentation.openrouter import OpenRouterInstrumentor

    Completions.create = lambda self, *a, **k: None
    instrumentors = [
        OpenAIInstrumentor(),
        OpenRouterInstrumentor(),
        OllamaInstrumentor(),
        GrokInstrumentor(),
    ]
    errors: list[Exception] = []

    def worker(inst: Any) -> None:
        try:
            for _ in range(10):
                inst.instrument()
                inst.uninstrument()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(inst,)) for inst in instrumentors]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    for inst in instrumentors:
        assert not inst.is_instrumented()
