"""
CrewAIInstrumentor — automatic CrewAI observability (EP-18.7).

    from costorah.instrumentation.crewai import CrewAIInstrumentor

    CrewAIInstrumentor().instrument()

    crew = Crew(agents=[...], tasks=[...])
    crew.kickoff()   # every agent, tool, task, and LLM call automatically
                      # generates telemetry

Hooks into CrewAI's own event bus (`crewai.events.crewai_event_bus`) —
CrewAI's official, documented extension point for observability
integrations (the same one CrewAI's own tracing/telemetry features use
internally), registering handlers via `crewai_event_bus.on(EventType)`.
No monkeypatching of CrewAI internals; no per-call code at any Crew/
Agent/Task/Tool construction site.

## What gets submitted as real usage telemetry, and what doesn't

Every `LLMCallCompletedEvent` (a real, completed LLM call — CrewAI's LLM
class normalizes usage across every underlying provider, via LiteLLM,
into one consistent `prompt_tokens`/`completion_tokens`/`total_tokens`
shape) submits a usage event through the existing
`costorah.instrumentation._submission`/reliability pipeline, with the
provider inferred from `event.model` (stripping a LiteLLM-style
`"openai/gpt-4o"` provider prefix when present, then matching against
`costorah.types.SUPPORTED_PROVIDERS` the same way
`costorah.instrumentation.langchain` does). If the model doesn't resolve
to a supported provider, **no usage event is submitted** — this
instrumentor never invents a provider.

`task_name`/`agent_role` (when CrewAI populates them on the completed
LLM call event — true whenever the call happens `from_task`/
`from_agent`, i.e. essentially always inside a real Crew run) are read
**directly from the LLM event's own fields**, not tracked across
separate event emissions. `event.event_id`/`event.parent_event_id` (also
CrewAI's own fields) are used as `span_id`/`parent_span_id` when
present.

This "read from the event itself, don't track state across events"
design is deliberate, not a simplification for its own sake: CrewAI's
event bus (`CrewAIEventsBus.emit`) dispatches each event's handlers via
`contextvars.copy_context()` + a thread-pool executor — **a fresh
context copy per `emit()` call, potentially on a different worker
thread each time**. This was discovered empirically (an earlier version
of this instrumentor tried to push ambient `costorah.context`
onto a stack at `on_tool_start`/`on_agent_start`/etc. and pop it at the
matching end event, mirroring `costorah.instrumentation.langchain`'s
approach) — it broke immediately with `contextvars.Token ... was
created in a different Context`, because a `ContextVar.set()` in one
handler invocation cannot be `.reset()` from a different invocation's
copied context. Chain/tool/agent/crew lifecycle events
(`AgentExecutionStartedEvent`/`ToolUsageStartedEvent`/
`TaskStartedEvent`/`CrewKickoffStartedEvent` and their `*Completed`/
`*Finished`/`*Failed` counterparts) are still handled — logged
(structured, debug level) and counted (`events_captured_total`) — but
do not attempt to enrich sibling LLM calls' metadata the way
`costorah.instrumentation.langchain`'s chain/tool spans do; only
`task_name`/`agent_role` (available directly on the LLM event) are
attached. `crew_name`/`tool_name` are not currently attached to LLM
usage events for this reason — see `sdk/docs/CREWAI.md`.

## Never captured

`ToolUsageEvent.tool_args` (the tool's actual arguments),
`LLMCallStartedEvent.messages`/`LLMCallCompletedEvent.response` (prompt/
response content), and `TaskCompletedEvent.output` are all present on
CrewAI's own event objects but never read by this instrumentor — only
name/ID/token-count/timing fields are.

## Combining with a provider instrumentor

Same caveat as `costorah.instrumentation.langchain`: don't also
`instrument()` a provider instrumentor for the same LLM calls CrewAI
already routes through its own `LLM` class, or the call will be
double-counted.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from costorah._logging import get_logger
from costorah.instrumentation._ai_common import (
    infer_provider_from_model,
    new_span_id,
    new_trace_id,
    resolve_cost,
)
from costorah.instrumentation._submission import submit
from costorah.instrumentation.base import ExtractedUsage

if TYPE_CHECKING:
    from crewai.events.types.agent_events import (
        AgentExecutionCompletedEvent,
        AgentExecutionErrorEvent,
        AgentExecutionStartedEvent,
    )
    from crewai.events.types.crew_events import (
        CrewKickoffCompletedEvent,
        CrewKickoffFailedEvent,
        CrewKickoffStartedEvent,
    )
    from crewai.events.types.llm_events import LLMCallCompletedEvent, LLMCallFailedEvent
    from crewai.events.types.task_events import (
        TaskCompletedEvent,
        TaskFailedEvent,
        TaskStartedEvent,
    )
    from crewai.events.types.tool_usage_events import (
        ToolUsageErrorEvent,
        ToolUsageFinishedEvent,
        ToolUsageStartedEvent,
    )

try:
    from crewai.events import crewai_event_bus
    from crewai.events.types.agent_events import (
        AgentExecutionCompletedEvent as _AgentCompleted,
    )
    from crewai.events.types.agent_events import (
        AgentExecutionErrorEvent as _AgentError,
    )
    from crewai.events.types.agent_events import (
        AgentExecutionStartedEvent as _AgentStarted,
    )
    from crewai.events.types.crew_events import CrewKickoffCompletedEvent as _CrewCompleted
    from crewai.events.types.crew_events import CrewKickoffFailedEvent as _CrewFailed
    from crewai.events.types.crew_events import CrewKickoffStartedEvent as _CrewStarted
    from crewai.events.types.llm_events import LLMCallCompletedEvent as _LLMCompleted
    from crewai.events.types.llm_events import LLMCallFailedEvent as _LLMFailed
    from crewai.events.types.task_events import TaskCompletedEvent as _TaskCompleted
    from crewai.events.types.task_events import TaskFailedEvent as _TaskFailed
    from crewai.events.types.task_events import TaskStartedEvent as _TaskStarted
    from crewai.events.types.tool_usage_events import ToolUsageErrorEvent as _ToolError
    from crewai.events.types.tool_usage_events import ToolUsageFinishedEvent as _ToolFinished
    from crewai.events.types.tool_usage_events import ToolUsageStartedEvent as _ToolStarted
except ImportError as exc:  # pragma: no cover - exercised only without crewai installed
    raise ImportError(
        "costorah.instrumentation.crewai requires 'crewai' to be installed. "
        "Install it with `pip install crewai` to use this instrumentor."
    ) from exc

_log = get_logger(__name__)


def _strip_litellm_provider_prefix(model: str) -> str:
    # CrewAI's LLM class accepts LiteLLM-style "provider/model" strings
    # (e.g. "openai/gpt-4o", "anthropic/claude-3-5-sonnet-20241022").
    return model.split("/", 1)[1] if "/" in model else model


class CostorahCrewAIListener:
    """Registers every handler this instrumentor needs. Not normally
    instantiated directly — `CrewAIInstrumentor().instrument()` creates
    and registers one."""

    def __init__(self) -> None:
        self.events_captured_total = 0
        self._handlers: dict[str, Any] = {}
        self._register()

    def _register(self) -> None:
        bus = crewai_event_bus

        @bus.on(_CrewStarted)  # type: ignore[untyped-decorator]
        def _on_crew_started(source: Any, event: CrewKickoffStartedEvent) -> None:
            self.events_captured_total += 1
            _log.debug("crewai_crew_started crew=%s", event.crew_name)

        @bus.on(_CrewCompleted)  # type: ignore[untyped-decorator]
        def _on_crew_completed(source: Any, event: CrewKickoffCompletedEvent) -> None:
            self.events_captured_total += 1
            _log.debug(
                "crewai_crew_completed crew=%s total_tokens=%d",
                event.crew_name,
                event.total_tokens,
            )

        @bus.on(_CrewFailed)  # type: ignore[untyped-decorator]
        def _on_crew_failed(source: Any, event: CrewKickoffFailedEvent) -> None:
            self.events_captured_total += 1
            _log.debug("crewai_crew_failed error=%s", event.error)

        @bus.on(_AgentStarted)  # type: ignore[untyped-decorator]
        def _on_agent_started(source: Any, event: AgentExecutionStartedEvent) -> None:
            self.events_captured_total += 1
            _log.debug("crewai_agent_started role=%s", getattr(event.agent, "role", None))

        @bus.on(_AgentCompleted)  # type: ignore[untyped-decorator]
        def _on_agent_completed(source: Any, event: AgentExecutionCompletedEvent) -> None:
            self.events_captured_total += 1

        @bus.on(_AgentError)  # type: ignore[untyped-decorator]
        def _on_agent_error(source: Any, event: AgentExecutionErrorEvent) -> None:
            self.events_captured_total += 1
            _log.debug("crewai_agent_error error=%s", event.error)

        @bus.on(_TaskStarted)  # type: ignore[untyped-decorator]
        def _on_task_started(source: Any, event: TaskStartedEvent) -> None:
            self.events_captured_total += 1

        @bus.on(_TaskCompleted)  # type: ignore[untyped-decorator]
        def _on_task_completed(source: Any, event: TaskCompletedEvent) -> None:
            self.events_captured_total += 1

        @bus.on(_TaskFailed)  # type: ignore[untyped-decorator]
        def _on_task_failed(source: Any, event: TaskFailedEvent) -> None:
            self.events_captured_total += 1
            _log.debug("crewai_task_failed error=%s", event.error)

        @bus.on(_ToolStarted)  # type: ignore[untyped-decorator]
        def _on_tool_started(source: Any, event: ToolUsageStartedEvent) -> None:
            self.events_captured_total += 1

        @bus.on(_ToolFinished)  # type: ignore[untyped-decorator]
        def _on_tool_finished(source: Any, event: ToolUsageFinishedEvent) -> None:
            self.events_captured_total += 1
            duration_ms = int((event.finished_at - event.started_at).total_seconds() * 1000)
            _log.debug(
                "crewai_tool_finished tool=%s duration_ms=%d", event.tool_name, duration_ms
            )

        @bus.on(_ToolError)  # type: ignore[untyped-decorator]
        def _on_tool_error(source: Any, event: ToolUsageErrorEvent) -> None:
            self.events_captured_total += 1
            _log.debug("crewai_tool_error tool=%s error=%s", event.tool_name, event.error)

        @bus.on(_LLMCompleted)  # type: ignore[untyped-decorator]
        def _on_llm_completed(source: Any, event: LLMCallCompletedEvent) -> None:
            self._submit_llm_usage(event)

        @bus.on(_LLMFailed)  # type: ignore[untyped-decorator]
        def _on_llm_failed(source: Any, event: LLMCallFailedEvent) -> None:
            self.events_captured_total += 1
            _log.debug("crewai_llm_call_failed error=%s", event.error)

        self._handlers = {
            "crew_started": _on_crew_started,
            "crew_completed": _on_crew_completed,
            "crew_failed": _on_crew_failed,
            "agent_started": _on_agent_started,
            "agent_completed": _on_agent_completed,
            "agent_error": _on_agent_error,
            "task_started": _on_task_started,
            "task_completed": _on_task_completed,
            "task_failed": _on_task_failed,
            "tool_started": _on_tool_started,
            "tool_finished": _on_tool_finished,
            "tool_error": _on_tool_error,
            "llm_completed": _on_llm_completed,
            "llm_failed": _on_llm_failed,
        }

    def unregister(self) -> None:
        off = getattr(crewai_event_bus, "off", None)
        if off is None:
            return
        event_types = {
            "crew_started": _CrewStarted,
            "crew_completed": _CrewCompleted,
            "crew_failed": _CrewFailed,
            "agent_started": _AgentStarted,
            "agent_completed": _AgentCompleted,
            "agent_error": _AgentError,
            "task_started": _TaskStarted,
            "task_completed": _TaskCompleted,
            "task_failed": _TaskFailed,
            "tool_started": _ToolStarted,
            "tool_finished": _ToolFinished,
            "tool_error": _ToolError,
            "llm_completed": _LLMCompleted,
            "llm_failed": _LLMFailed,
        }
        for key, handler in self._handlers.items():
            with contextlib.suppress(Exception):
                off(event_types[key], handler)
        self._handlers = {}

    def _submit_llm_usage(self, event: LLMCallCompletedEvent) -> None:
        self.events_captured_total += 1
        usage = event.usage or {}
        model = _strip_litellm_provider_prefix(event.model or "unknown")
        provider = infer_provider_from_model(model)
        if provider is None:
            _log.debug(
                "crewai_llm_call_not_submitted model=%s reason=unrecognized_provider", model
            )
            return

        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        cost, was_estimated = resolve_cost(provider, model, input_tokens, output_tokens)

        metadata: dict[str, Any] = {
            "trace_id": new_trace_id(),
            "span_id": event.event_id or new_span_id(),
            "parent_span_id": event.parent_event_id,
            "framework": "crewai",
            "cost_estimated": was_estimated,
        }
        if event.task_name:
            metadata["task_name"] = event.task_name
        if event.agent_role:
            metadata["agent_role"] = event.agent_role
        if event.finish_reason:
            metadata["finish_reason"] = event.finish_reason
        reasoning = usage.get("reasoning_tokens")
        if reasoning:
            metadata["reasoning_tokens"] = reasoning

        submit(
            ExtractedUsage(
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_tokens=usage.get("cached_prompt_tokens"),
                total_tokens=usage.get("total_tokens"),
                cost=cost,
                status="success",
                request_id=event.call_id or event.event_id,
                metadata=metadata,
            )
        )


class CrewAIInstrumentor:
    """`CrewAIInstrumentor().instrument()` registers a
    `CostorahCrewAIListener` with CrewAI's event bus. Idempotent, same
    contract as every other instrumentor in this SDK."""

    name = "crewai"

    def __init__(self) -> None:
        self._listener: CostorahCrewAIListener | None = None

    def instrument(self) -> None:
        if self._listener is not None:
            _log.debug("already_instrumented provider=crewai")
            return
        self._listener = CostorahCrewAIListener()
        _log.info("instrumentation_enabled provider=crewai")

    def uninstrument(self) -> None:
        if self._listener is None:
            return
        self._listener.unregister()
        self._listener = None
        _log.info("instrumentation_disabled_restored provider=crewai")

    def is_instrumented(self) -> bool:
        return self._listener is not None

    @property
    def events_captured_total(self) -> int:
        return self._listener.events_captured_total if self._listener else 0
