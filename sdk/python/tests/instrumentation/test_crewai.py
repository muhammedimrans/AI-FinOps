from __future__ import annotations

from typing import Any

import httpx
import pytest

crewai = pytest.importorskip("crewai")

from crewai.events import crewai_event_bus  # noqa: E402
from crewai.events.types.agent_events import (  # noqa: E402
    AgentExecutionCompletedEvent,
    AgentExecutionStartedEvent,
)
from crewai.events.types.crew_events import (  # noqa: E402
    CrewKickoffCompletedEvent,
    CrewKickoffStartedEvent,
)
from crewai.events.types.llm_events import (  # noqa: E402
    LLMCallCompletedEvent,
    LLMCallFailedEvent,
    LLMCallStartedEvent,
    LLMCallType,
)
from crewai.events.types.task_events import TaskCompletedEvent, TaskStartedEvent  # noqa: E402
from crewai.events.types.tool_usage_events import (  # noqa: E402
    ToolUsageFinishedEvent,
    ToolUsageStartedEvent,
)

from costorah.client import Costorah  # noqa: E402
from costorah.instrumentation import set_default_client  # noqa: E402
from costorah.instrumentation._submission import reset_default_client_for_tests  # noqa: E402
from costorah.instrumentation.crewai import CrewAIInstrumentor  # noqa: E402


class _FakeSource:
    id = "fake-source"


def _emit(event: Any) -> None:
    """Emits an event and blocks until every handler has actually run —
    CrewAI's event bus dispatches sync handlers on a thread-pool executor
    (see costorah.instrumentation.crewai's module docstring), so tests
    must wait on the returned Future rather than assume synchronous
    completion."""
    future = crewai_event_bus.emit(_FakeSource(), event=event)
    if future is not None:
        future.result(timeout=5.0)


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


class TestLLMUsageCapture:
    def test_llm_call_completed_submits_real_usage(self) -> None:
        captured: list[dict] = []
        client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
        set_default_client(client)

        instrumentor = CrewAIInstrumentor()
        instrumentor.instrument()
        try:
            _emit(
                LLMCallStartedEvent(
                    model="gpt-4o-mini", call_id="call1", call_type=LLMCallType.LLM_CALL
                )
            )
            _emit(
                LLMCallCompletedEvent(
                    model="gpt-4o-mini",
                    call_id="call1",
                    call_type=LLMCallType.LLM_CALL,
                    response="the actual response text — never captured",
                    usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                    finish_reason="stop",
                    task_name="Research the topic",
                    agent_role="researcher",
                )
            )

            client.flush(timeout=5)
            assert len(captured) == 1
            event = captured[0]
            assert event["provider"] == "openai"
            assert event["model"] == "gpt-4o-mini"
            assert event["input_tokens"] == 20
            assert event["output_tokens"] == 10
            assert event["cost"] > 0
            assert event["metadata"]["framework"] == "crewai"
            assert event["metadata"]["task_name"] == "Research the topic"
            assert event["metadata"]["agent_role"] == "researcher"
            assert event["metadata"]["finish_reason"] == "stop"
            assert event["metadata"]["trace_id"].startswith("trace_")

            payload_str = str(event)
            assert "the actual response text" not in payload_str
        finally:
            instrumentor.uninstrument()
            client.shutdown()

    def test_strips_litellm_provider_prefix_from_model(self) -> None:
        captured: list[dict] = []
        client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
        set_default_client(client)

        instrumentor = CrewAIInstrumentor()
        instrumentor.instrument()
        try:
            _emit(
                LLMCallCompletedEvent(
                    model="openai/gpt-4o-mini",
                    call_id="call2",
                    call_type=LLMCallType.LLM_CALL,
                    response="r",
                    usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                )
            )
            client.flush(timeout=5)
            assert captured[0]["model"] == "gpt-4o-mini"
            assert captured[0]["provider"] == "openai"
        finally:
            instrumentor.uninstrument()
            client.shutdown()

    def test_unrecognized_model_does_not_submit(self) -> None:
        captured: list[dict] = []
        client = Costorah(api_key="costorah_live_x", _transport=_echo_transport(captured))
        set_default_client(client)

        instrumentor = CrewAIInstrumentor()
        instrumentor.instrument()
        try:
            _emit(
                LLMCallCompletedEvent(
                    model="my-self-hosted-llama",
                    call_id="call3",
                    call_type=LLMCallType.LLM_CALL,
                    response="r",
                    usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                )
            )
            client.flush(timeout=5)
            assert captured == []
        finally:
            instrumentor.uninstrument()
            client.shutdown()

    def test_llm_call_failed_does_not_raise_and_is_counted(self) -> None:
        instrumentor = CrewAIInstrumentor()
        instrumentor.instrument()
        try:
            before = instrumentor.events_captured_total
            _emit(
                LLMCallFailedEvent(
                    model="gpt-4o-mini",
                    call_id="call4",
                    call_type=LLMCallType.LLM_CALL,
                    error="boom",
                )
            )
            assert instrumentor.events_captured_total == before + 1
        finally:
            instrumentor.uninstrument()


class TestLifecycleEventsAreCountedAndDoNotRaise:
    def test_crew_agent_task_tool_events_all_increment_the_counter(self) -> None:
        instrumentor = CrewAIInstrumentor()
        instrumentor.instrument()
        try:
            before = instrumentor.events_captured_total

            _emit(CrewKickoffStartedEvent(crew_name="TestCrew", inputs={}))
            _emit(CrewKickoffCompletedEvent(crew_name="TestCrew", output="done", total_tokens=42))

            from crewai import Agent

            agent = Agent(role="researcher", goal="find stuff", backstory="an agent")

            _emit(
                AgentExecutionStartedEvent(
                    agent=agent, task=None, tools=None, task_prompt="prompt"
                )
            )
            _emit(AgentExecutionCompletedEvent(agent=agent, task=None, output="out"))

            from crewai.tasks.task_output import TaskOutput

            _emit(TaskStartedEvent(context=None, task=None))
            _emit(
                TaskCompletedEvent(
                    output=TaskOutput(raw="output", description="desc", agent="researcher"),
                    task=None,
                )
            )

            _emit(
                ToolUsageStartedEvent(
                    tool_name="search", tool_args={"query": "secret query — never logged"}
                )
            )
            import datetime

            now = datetime.datetime.now(datetime.timezone.utc)
            _emit(
                ToolUsageFinishedEvent(
                    tool_name="search",
                    tool_args={"query": "secret"},
                    started_at=now,
                    finished_at=now,
                    output="tool output",
                )
            )

            assert instrumentor.events_captured_total == before + 8
        finally:
            instrumentor.uninstrument()


class TestCrewAIInstrumentorLifecycle:
    def test_instrument_is_idempotent(self) -> None:
        instrumentor = CrewAIInstrumentor()
        instrumentor.instrument()
        first_listener = instrumentor._listener
        instrumentor.instrument()
        assert instrumentor._listener is first_listener
        instrumentor.uninstrument()

    def test_uninstrument_clears_state_and_stops_capturing(self) -> None:
        instrumentor = CrewAIInstrumentor()
        instrumentor.instrument()
        assert instrumentor.is_instrumented() is True
        instrumentor.uninstrument()
        assert instrumentor.is_instrumented() is False

        before = instrumentor.events_captured_total
        _emit(CrewKickoffStartedEvent(crew_name="AfterUninstrument", inputs={}))
        assert instrumentor.events_captured_total == before == 0
