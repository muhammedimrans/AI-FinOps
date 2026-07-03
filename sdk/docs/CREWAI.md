# CrewAI (Python)

```python
from crewai import Agent, Task, Crew
from costorah.instrumentation.crewai import CrewAIInstrumentor

CrewAIInstrumentor().instrument()

crew = Crew(agents=[...], tasks=[...])
crew.kickoff()   # every LLM call inside the crew automatically generates
                  # telemetry
```

## How it works

Hooks into CrewAI's own event bus (`crewai.events.crewai_event_bus`) —
CrewAI's documented, official observability extension point — registering
handlers via `crewai_event_bus.on(EventType)` for crew/agent/task/tool/LLM
start, completion, and failure events. No monkeypatching of CrewAI
internals.

## What gets captured

Every `LLMCallCompletedEvent` (a real, completed LLM call — CrewAI's `LLM`
class normalizes usage across every underlying provider, via LiteLLM, into
one `prompt_tokens`/`completion_tokens`/`total_tokens` shape) submits a
usage event: `provider` (inferred from `event.model`, stripping a
LiteLLM-style `"openai/gpt-4o"` prefix when present), `model`,
`input_tokens`, `output_tokens`, `cost`, `finish_reason`, and — when
present — `task_name`/`agent_role`, read **directly from the event's own
fields** (CrewAI populates these automatically whenever the call happens
`from_task`/`from_agent`, essentially always inside a real crew run).
`trace_id` is generated fresh per event; `span_id`/`parent_span_id` use
CrewAI's own `event.event_id`/`event.parent_event_id`.

Crew/agent/task/tool lifecycle events are counted
(`events_captured_total`) and logged (debug level) but never
independently submit usage — see `AI_FRAMEWORK_INTEGRATIONS.md`.

## Why this instrumentor's design differs from LangChain's

CrewAI's event bus (`CrewAIEventsBus.emit`) dispatches every event's
handlers via `contextvars.copy_context()` submitted to a
`ThreadPoolExecutor` — **a fresh context copy per `emit()` call,
potentially on a different worker thread each time**. An earlier version
of this instrumentor mirrored `costorah.instrumentation.langchain`'s
design (push ambient context at `*_started`, pop at the matching
`*_completed`) and immediately crashed with
`contextvars.Token ... was created in a different Context` — a
`ContextVar.set()` in one handler invocation cannot be `.reset()` from a
different invocation's copied context. Fixed by reading
`task_name`/`agent_role`/`event_id`/`parent_event_id` directly off each
`LLMCallCompletedEvent`'s own fields instead of tracking state across
separate event emissions — genuinely simpler and more correct than the
original design, not just a workaround.

## Provider resolution

`event.model` (after stripping any LiteLLM-style provider prefix) is
matched against known model-name prefixes. If it doesn't resolve to a
member of `SUPPORTED_PROVIDERS`, **no usage event is submitted**.

## Combining with a provider instrumentor

Don't also instrument a provider SDK for the same LLM calls CrewAI already
routes through its own `LLM` class — double-counting.

## Never captured

`ToolUsageEvent.tool_args`, `LLMCallStartedEvent.messages`/
`LLMCallCompletedEvent.response`, and `TaskCompletedEvent.output` are
present on CrewAI's own event objects but never read here.

## Verified against

Real `crewai` package — a real `Agent`/`TaskOutput`, real event bus
emission (waiting on the returned `Future` from `emit()`, since dispatch
is thread-pool-based), asserting correct `provider`/`model`/`cost`/
`task_name`/`agent_role`/`trace_id` in the captured payload.
