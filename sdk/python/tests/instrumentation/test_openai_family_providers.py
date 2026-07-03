"""
Tests for the other four OpenAI-SDK-compatible instrumentors (Azure,
OpenRouter, Ollama, Grok): provider detection via base_url/class name,
and the "only active family members receive telemetry" scoping rule.
Deep coverage of the shared patch mechanics (streaming, async, error
paths, restore) already lives in test_openai_instrumentation.py — these
tests focus on what's unique to each provider: identity detection.
"""

from __future__ import annotations

from typing import Any

import pytest

openai = pytest.importorskip("openai")

from openai import AzureOpenAI, OpenAI  # noqa: E402
from openai.resources.chat.completions import Completions  # noqa: E402
from openai.types.chat.chat_completion import ChatCompletion  # noqa: E402
from openai.types.completion_usage import CompletionUsage  # noqa: E402

from costorah.instrumentation.azure_openai import AzureOpenAIInstrumentor  # noqa: E402
from costorah.instrumentation.grok import GrokInstrumentor  # noqa: E402
from costorah.instrumentation.ollama import OllamaInstrumentor  # noqa: E402
from costorah.instrumentation.openai import OpenAIInstrumentor  # noqa: E402
from costorah.instrumentation.openrouter import OpenRouterInstrumentor  # noqa: E402

_PRISTINE_CREATE = Completions.__dict__["create"]


@pytest.fixture(autouse=True)
def _clean_state() -> Any:
    yield
    Completions.create = _PRISTINE_CREATE


def _completion(model: str = "m") -> ChatCompletion:
    return ChatCompletion(
        id="c1",
        object="chat.completion",
        created=0,
        model=model,
        choices=[
            {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
        ],
        usage=CompletionUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def test_openrouter_detected_via_base_url(captured_submissions: list[Any]) -> None:
    Completions.create = lambda self, *a, **k: _completion()
    inst = OpenRouterInstrumentor()
    inst.instrument()
    client = OpenAI(api_key="k", base_url="https://openrouter.ai/api/v1")
    client.chat.completions.create(model="openai/gpt-4o", messages=[])
    inst.uninstrument()
    assert captured_submissions[0].provider == "openrouter"


def test_ollama_detected_via_localhost_base_url(captured_submissions: list[Any]) -> None:
    Completions.create = lambda self, *a, **k: _completion()
    inst = OllamaInstrumentor()
    inst.instrument()
    client = OpenAI(api_key="ollama", base_url="http://localhost:11434/v1")
    client.chat.completions.create(model="llama3", messages=[])
    inst.uninstrument()
    assert captured_submissions[0].provider == "ollama"


def test_grok_detected_via_x_ai_base_url(captured_submissions: list[Any]) -> None:
    Completions.create = lambda self, *a, **k: _completion()
    inst = GrokInstrumentor()
    inst.instrument()
    client = OpenAI(api_key="k", base_url="https://api.x.ai/v1")
    client.chat.completions.create(model="grok-2", messages=[])
    inst.uninstrument()
    assert captured_submissions[0].provider == "grok"


def test_azure_detected_via_client_class() -> None:
    Completions.create = lambda self, *a, **k: _completion()
    inst = AzureOpenAIInstrumentor()
    inst.instrument()

    captured: list[Any] = []
    import costorah.instrumentation._openai_compatible as oc

    real_submit = oc.submit
    oc.submit = lambda usage, client=None: captured.append(usage) or True
    try:
        client = AzureOpenAI(
            api_key="k", azure_endpoint="https://example.openai.azure.com", api_version="2024-01-01"
        )
        client.chat.completions.create(model="my-deployment", messages=[])
    finally:
        oc.submit = real_submit
        inst.uninstrument()

    assert captured[0].provider == "azure_openai"


def test_only_active_family_member_receives_telemetry(captured_submissions: list[Any]) -> None:
    """Instrumenting only OpenAIInstrumentor must not capture traffic
    through an OpenRouter-targeted client — no OpenRouterInstrumentor is
    active, so that provider's traffic is silently not captured, matching
    how every reference APM SDK scopes "what's on"."""
    Completions.create = lambda self, *a, **k: _completion()
    inst = OpenAIInstrumentor()
    inst.instrument()
    client = OpenAI(api_key="k", base_url="https://openrouter.ai/api/v1")
    client.chat.completions.create(model="openai/gpt-4o", messages=[])
    inst.uninstrument()
    assert captured_submissions == []


def test_multiple_family_members_instrumented_simultaneously(
    captured_submissions: list[Any],
) -> None:
    Completions.create = lambda self, *a, **k: _completion()
    openai_inst = OpenAIInstrumentor()
    openrouter_inst = OpenRouterInstrumentor()
    openai_inst.instrument()
    openrouter_inst.instrument()

    OpenAI(api_key="k").chat.completions.create(model="gpt-4o", messages=[])
    OpenAI(api_key="k", base_url="https://openrouter.ai/api/v1").chat.completions.create(
        model="openai/gpt-4o", messages=[]
    )

    openai_inst.uninstrument()
    assert openrouter_inst.is_instrumented()  # sibling still active
    openrouter_inst.uninstrument()

    providers = sorted(u.provider for u in captured_submissions)
    assert providers == ["openai", "openrouter"]


def test_uninstrumenting_one_sibling_does_not_break_the_other(
    captured_submissions: list[Any],
) -> None:
    fake_create = lambda self, *a, **k: _completion()  # noqa: E731
    Completions.create = fake_create
    openai_inst = OpenAIInstrumentor()
    openrouter_inst = OpenRouterInstrumentor()
    openai_inst.instrument()
    openrouter_inst.instrument()
    patched_create = Completions.__dict__["create"]

    openai_inst.uninstrument()  # openrouter's patch must survive
    assert Completions.__dict__["create"] is patched_create  # not restored yet

    OpenAI(api_key="k", base_url="https://openrouter.ai/api/v1").chat.completions.create(
        model="openai/gpt-4o", messages=[]
    )
    openrouter_inst.uninstrument()

    assert len(captured_submissions) == 1
    assert captured_submissions[0].provider == "openrouter"
    # Fully restored now that the last family member uninstrumented —
    # back to the fake `create` this test itself installed (not
    # necessarily the SDK's true pristine method, since that's what was
    # captured as "original" at the moment instrument() first ran).
    assert Completions.__dict__["create"] is fake_create
