from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest

langchain_core = pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, LLMResult  # noqa: E402

from costorah.client import Costorah  # noqa: E402
from costorah.context import get_request_context  # noqa: E402
from costorah.instrumentation import set_default_client  # noqa: E402
from costorah.instrumentation._ai_common import (  # noqa: E402
    infer_provider_from_model,
    infer_provider_from_module_path,
)
from costorah.instrumentation._submission import reset_default_client_for_tests  # noqa: E402
from costorah.instrumentation.langchain import (  # noqa: E402
    CostorahLangChainHandler,
    LangChainInstrumentor,
    _extract_finish_reason,
    _extract_usage_metadata,
)


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    reset_default_client_for_tests()
    yield
    reset_default_client_for_tests()


def _echo_transport(captured: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "success": True,
                "usage_id": "u1",
                "request_id": captured[-1]["request_id"],
                "processed_at": "2026-01-01T00:00:00Z",
                "duplicate": False,
            },
        )

    return httpx.MockTransport(handler)


def _chat_llm_result(
    *,
    model: str = "gpt-4o-mini",
    input_tokens: int = 10,
    output_tokens: int = 5,
    reasoning_tokens: int | None = None,
    cached_tokens: int | None = None,
    finish_reason: str = "stop",
    content: str = "this is the actual response text, never captured",
) -> LLMResult:
    usage_metadata: dict[str, Any] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    if reasoning_tokens is not None:
        usage_metadata["output_token_details"] = {"reasoning": reasoning_tokens}
    if cached_tokens is not None:
        usage_metadata["input_token_details"] = {"cache_read": cached_tokens}

    message = AIMessage(content=content, usage_metadata=usage_metadata)  # type: ignore[arg-type]
    generation = ChatGeneration(message=message, generation_info={"finish_reason": finish_reason})
    return LLMResult(generations=[[generation]], llm_output={"model_name": model})


class TestProviderInference:
    def test_module_path_maps_known_langchain_provider_packages(self) -> None:
        assert infer_provider_from_module_path("langchain_openai.chat_models.base") == "openai"
        assert infer_provider_from_module_path("langchain_anthropic.chat_models") == "anthropic"
        assert infer_provider_from_module_path("langchain_mistralai.chat_models") == "mistral"

    def test_module_path_unknown_package_returns_none(self) -> None:
        assert infer_provider_from_module_path("some_random_package.chat_models") is None

    def test_model_name_prefix_inference(self) -> None:
        assert infer_provider_from_model("gpt-4o-mini") == "openai"
        assert infer_provider_from_model("claude-3-5-sonnet-20241022") == "anthropic"
        assert infer_provider_from_model("totally-unknown-model") is None


class TestUsageExtraction:
    def test_extracts_standardized_usage_metadata(self) -> None:
        result = _chat_llm_result(
            input_tokens=100, output_tokens=42, reasoning_tokens=7, cached_tokens=3
        )
        usage = _extract_usage_metadata(result)
        assert usage is not None
        assert usage["input_tokens"] == 100
        assert usage["output_tokens"] == 42
        assert usage["total_tokens"] == 142
        assert usage["reasoning_tokens"] == 7
        assert usage["cached_tokens"] == 3

    def test_extracts_finish_reason(self) -> None:
        result = _chat_llm_result(finish_reason="length")
        assert _extract_finish_reason(result) == "length"

    def test_falls_back_to_llm_output_token_usage_for_non_chat_llms(self) -> None:
        result = LLMResult(
            generations=[[]],
            llm_output={
                "model_name": "gpt-3.5-turbo-instruct",
                "token_usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            },
        )
        usage = _extract_usage_metadata(result)
        assert usage == {
            "model": "gpt-3.5-turbo-instruct",
            "input_tokens": 20,
            "output_tokens": 8,
            "total_tokens": 28,
            "cached_tokens": None,
            "reasoning_tokens": None,
        }

    def test_no_usage_data_returns_none(self) -> None:
        result = LLMResult(generations=[[]], llm_output={})
        assert _extract_usage_metadata(result) is None


class TestCostorahLangChainHandlerDirectly:
    """Exercises the handler's public BaseCallbackHandler methods
    directly — these are the exact methods LangChain itself calls, so
    this is testing the real integration surface without needing a full
    LangChain runtime for every scenario."""

    def test_llm_call_submits_usage_with_trace_context(
        self, captured_submissions: list[Any]
    ) -> None:
        handler = CostorahLangChainHandler()
        run_id = uuid.uuid4()
        handler.on_chat_model_start(
            {"id": ["langchain_openai", "chat_models", "base", "ChatOpenAI"]},
            [],
            run_id=run_id,
        )
        handler.on_llm_end(_chat_llm_result(), run_id=run_id)

        assert len(captured_submissions) == 1
        usage = captured_submissions[0]
        assert usage.provider == "openai"
        assert usage.model == "gpt-4o-mini"
        assert usage.input_tokens == 10
        assert usage.output_tokens == 5
        assert usage.cost > 0
        assert usage.metadata["trace_id"].startswith("trace_")
        assert usage.metadata["span_id"].startswith("span_")
        assert usage.metadata["parent_span_id"] is None
        assert usage.metadata["framework"] == "langchain"
        assert usage.metadata["finish_reason"] == "stop"

    def test_unrecognized_model_does_not_submit(self, captured_submissions: list[Any]) -> None:
        handler = CostorahLangChainHandler()
        run_id = uuid.uuid4()
        handler.on_chat_model_start({"id": ["some_custom_package", "MyLLM"]}, [], run_id=run_id)
        handler.on_llm_end(
            _chat_llm_result(model="totally-custom-self-hosted-model"), run_id=run_id
        )
        assert captured_submissions == []

    def test_nested_llm_call_inherits_parent_trace_id(
        self, captured_submissions: list[Any]
    ) -> None:
        handler = CostorahLangChainHandler()
        chain_run_id = uuid.uuid4()
        llm_run_id = uuid.uuid4()

        handler.on_chain_start({"id": ["some_chain", "MyChain"]}, {}, run_id=chain_run_id)
        handler.on_chat_model_start(
            {"id": ["langchain_openai", "chat_models", "base", "ChatOpenAI"]},
            [],
            run_id=llm_run_id,
            parent_run_id=chain_run_id,
        )
        handler.on_llm_end(_chat_llm_result(), run_id=llm_run_id, parent_run_id=chain_run_id)
        handler.on_chain_end({}, run_id=chain_run_id)

        assert len(captured_submissions) == 1
        usage = captured_submissions[0]
        assert usage.metadata["parent_span_id"] == str(chain_run_id)
        # The chain's ambient context (chain_name) enriches the nested LLM call.
        assert usage.metadata["chain_name"] == "MyChain"

    def test_tool_context_enriches_nested_llm_call(self, captured_submissions: list[Any]) -> None:
        handler = CostorahLangChainHandler()
        tool_run_id = uuid.uuid4()
        llm_run_id = uuid.uuid4()

        handler.on_tool_start(
            {"id": ["some_tool", "MyTool"], "name": "MyTool"}, "input", run_id=tool_run_id
        )
        handler.on_chat_model_start(
            {"id": ["langchain_openai", "chat_models", "base", "ChatOpenAI"]},
            [],
            run_id=llm_run_id,
            parent_run_id=tool_run_id,
        )
        handler.on_llm_end(_chat_llm_result(), run_id=llm_run_id, parent_run_id=tool_run_id)
        handler.on_tool_end("output", run_id=tool_run_id)

        assert len(captured_submissions) == 1
        assert captured_submissions[0].metadata["tool_name"] == "MyTool"

    def test_context_does_not_leak_after_chain_ends(self) -> None:
        handler = CostorahLangChainHandler()
        chain_run_id = uuid.uuid4()
        handler.on_chain_start({"id": ["c", "MyChain"]}, {}, run_id=chain_run_id)
        assert get_request_context() == {"chain_name": "MyChain"}
        handler.on_chain_end({}, run_id=chain_run_id)
        assert get_request_context() is None

    def test_chain_error_still_clears_context(self) -> None:
        handler = CostorahLangChainHandler()
        chain_run_id = uuid.uuid4()
        handler.on_chain_start({"id": ["c", "MyChain"]}, {}, run_id=chain_run_id)
        handler.on_chain_error(ValueError("boom"), run_id=chain_run_id)
        assert get_request_context() is None

    def test_events_captured_total_counts_every_lifecycle_event(self) -> None:
        handler = CostorahLangChainHandler()
        run_id = uuid.uuid4()
        handler.on_chain_start({"id": ["c", "MyChain"]}, {}, run_id=run_id)
        handler.on_chain_end({}, run_id=run_id)
        assert handler.events_captured_total == 1


class TestLangChainInstrumentorLifecycle:
    def test_instrument_is_idempotent(self) -> None:
        instrumentor = LangChainInstrumentor()
        instrumentor.instrument()
        first_handler = instrumentor._handler
        instrumentor.instrument()
        assert instrumentor._handler is first_handler
        instrumentor.uninstrument()

    def test_uninstrument_clears_state(self) -> None:
        instrumentor = LangChainInstrumentor()
        instrumentor.instrument()
        assert instrumentor.is_instrumented() is True
        instrumentor.uninstrument()
        assert instrumentor.is_instrumented() is False


def test_end_to_end_via_real_chatopenai() -> None:
    """Full integration: a real ChatOpenAI instance, with the OpenAI SDK's
    actual HTTP boundary mocked (not any LangChain-internal method) —
    proves LangChainInstrumentor works with LangChain's real invoke()
    call path, not just direct handler-method calls."""
    chat_openai = pytest.importorskip("langchain_openai")

    def openai_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi there"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    set_default_client(client)

    instrumentor = LangChainInstrumentor()
    instrumentor.instrument()
    try:
        chat_model = chat_openai.ChatOpenAI(
            api_key="sk-fake",
            model="gpt-4o-mini",
            http_client=httpx.Client(transport=httpx.MockTransport(openai_handler)),
        )
        result = chat_model.invoke("Hello")
        assert result.content == "hi there"

        client.flush(timeout=5)
        assert len(captured) == 1
        event = captured[0]
        assert event["provider"] == "openai"
        assert event["model"] == "gpt-4o-mini"
        assert event["input_tokens"] == 10
        assert event["output_tokens"] == 5
        assert event["metadata"]["framework"] == "langchain"

        # Privacy: the prompt ("Hello") and response ("hi there") text
        # must never appear anywhere in the submitted payload.
        payload_str = str(event)
        assert "Hello" not in payload_str
        assert "hi there" not in payload_str
    finally:
        instrumentor.uninstrument()
        client.shutdown()


def test_end_to_end_via_real_runnable_sequence_prompt_pipe_model() -> None:
    """Regression test: a real `prompt | model` RunnableSequence calls
    `on_chain_start` with `serialized=None` for some of its internal
    steps (found empirically while verifying the LangChain example app,
    not from LangChain's type hints alone — the crash was
    `AttributeError: 'NoneType' object has no attribute 'get'`). Usage
    capture for the nested LLM call must still succeed."""
    chat_openai = pytest.importorskip("langchain_openai")
    prompts_module = pytest.importorskip("langchain_core.prompts")

    def openai_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi there"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    captured: list[dict] = []
    client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
    set_default_client(client)

    instrumentor = LangChainInstrumentor()
    instrumentor.instrument()
    try:
        chat_model = chat_openai.ChatOpenAI(
            api_key="sk-fake",
            model="gpt-4o-mini",
            http_client=httpx.Client(transport=httpx.MockTransport(openai_handler)),
        )
        prompt = prompts_module.ChatPromptTemplate.from_template("Say hi to {name}.")
        chain = prompt | chat_model

        result = chain.invoke({"name": "COSTORAH"})
        assert result.content == "hi there"

        client.flush(timeout=5)
        assert len(captured) == 1
        event = captured[0]
        assert event["provider"] == "openai"
        assert event["model"] == "gpt-4o-mini"
    finally:
        instrumentor.uninstrument()
        client.shutdown()
