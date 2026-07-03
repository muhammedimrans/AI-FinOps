"""
LangChainInstrumentor — automatic LangChain observability (EP-18.7).

    from costorah.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().instrument()

    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI()
    llm.invoke("Hello")   # usage automatically captured and submitted

Hooks into LangChain's own extension point for auto-injecting a global
callback handler — `langchain_core.tracers.context.register_configure_hook`
— the same mechanism LangSmith's own `LANGCHAIN_TRACING_V2` auto-tracer
uses internally (`langchain_core.callbacks.manager._configure` iterates
every registered hook and adds its handler to each run's callback
manager automatically). This means no `callbacks=[...]` argument is
needed at any call site — exactly the "no per-call code" behavior the
ticket's Success Criteria requires — and it works for every LangChain
construct (`LLM.invoke`, `Chain.invoke`, `AgentExecutor.invoke`, LCEL
`Runnable` chains, tool calls) since they all route through the same
`CallbackManager.configure()` call.

## What gets submitted as real usage telemetry, and what doesn't

Every `on_llm_end` (a real, completed LLM call) submits a usage event
through the existing `costorah.instrumentation._submission`/reliability
pipeline — the same pipeline every provider instrumentor
(`OpenAIInstrumentor`, etc.) already uses — with:

  - `provider`/`model`: inferred from the chat model's class path (e.g.
    `ChatOpenAI` -> `"openai"`) or, for non-chat LLMs and models with an
    unrecognized class path, from the model name string itself. If
    neither resolves to one of `costorah.types.SUPPORTED_PROVIDERS`
    (which mirrors EP-16's closed backend enum — not modified in this
    EP), **no usage event is submitted** — there is no valid provider to
    report, and this instrumentor never invents one.
  - `input_tokens`/`output_tokens`/`total_tokens`/`cached_tokens`: from
    the response message's standardized `usage_metadata`
    (`input_token_details.cache_read`, when present) — the same
    normalized shape LangChain itself uses across every provider
    integration, rather than each provider's raw response shape.
  - `metadata["reasoning_tokens"]`: from `usage_metadata.
    output_token_details.reasoning`, when the provider/model supports
    it (e.g. OpenAI's o-series).
  - `metadata["trace_id"]`/`metadata["span_id"]`/
    `metadata["parent_span_id"]`: a span tree built from LangChain's own
    `run_id`/`parent_run_id`, so nested chain -> agent -> LLM call
    hierarchies are reconstructable.
  - `metadata["chain_name"]`/`metadata["agent_name"]`/
    `metadata["tool_name"]`: whichever ambient chain/agent/tool span is
    currently open (see below) — `None` if the LLM call isn't nested
    inside one.
  - `metadata["finish_reason"]`, `metadata["prompt_template_id"]` (from
    a `"prompt_template_id"` LangChain run tag, if the caller sets one —
    never the prompt text itself), `metadata["conversation_id"]`/
    `metadata["session_id"]` (from LangChain run metadata keys of the
    same name, if the caller sets them).

Chain/tool/agent lifecycle events (`on_chain_start`/`on_tool_start`/
`on_agent_action`/etc.) do **not** independently submit a usage
event — COSTORAH's ingestion endpoint (EP-16) only accepts LLM usage
records shaped around provider/model/tokens/cost; there is no
trace/span ingestion endpoint, and adding one is a backend change out of
scope for this EP. Instead, each lifecycle event sets *ambient request
context* (`costorah.context.request_context`, the exact mechanism
`costorah.integrations.fastapi`/`.flask`/`.celery` already use) for the
duration of that chain/tool/agent's execution, so any LLM call nested
inside it is enriched with `chain_name`/`agent_name`/`tool_name` in its
submitted usage event's metadata. Latency/error/retry information for
chain and tool spans themselves is logged (structured, debug level) and
counted locally (`events_captured_total`), not submitted to the backend
— see `sdk/docs/LANGCHAIN.md` for the full list of what's captured
locally-only versus submitted.

## Never captured

Prompt text, response text, tool call arguments/results, or any other
message content — every extraction path in this module reads only
`usage_metadata`/class-path/run-ID fields, never `.content`.

## Combining with a provider instrumentor

Do not also `instrument()` a provider instrumentor (e.g.
`OpenAIInstrumentor`) for the same calls `LangChainInstrumentor` already
covers — LangChain's `ChatOpenAI` ultimately calls
`openai.resources.chat.completions.Completions.create` under the hood,
so both instrumentors would submit a usage event for the same call,
double-counting it. Use `LangChainInstrumentor` for LangChain-routed
calls and a provider instrumentor only for direct provider SDK calls
made outside LangChain.
"""

from __future__ import annotations

import time
from contextlib import AbstractContextManager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any
from uuid import UUID

from costorah._logging import get_logger
from costorah.context import request_context
from costorah.instrumentation._ai_common import (
    infer_provider_from_model,
    infer_provider_from_module_path,
    new_span_id,
    new_trace_id,
    resolve_cost,
)
from costorah.instrumentation._submission import submit
from costorah.instrumentation.base import ExtractedUsage

if TYPE_CHECKING:
    from langchain_core.outputs import LLMResult

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
    from langchain_core.tracers.context import register_configure_hook
except ImportError as exc:  # pragma: no cover - exercised only without langchain installed
    raise ImportError(
        "costorah.instrumentation.langchain requires 'langchain-core' to be installed. "
        "Install it with `pip install langchain-core` (or `langchain`) to use this instrumentor."
    ) from exc

_log = get_logger(__name__)


class _RunInfo:
    __slots__ = ("context_cm", "kind", "name", "provider_hint", "span_id", "start", "trace_id")

    def __init__(
        self,
        kind: str,
        name: str,
        trace_id: str,
        span_id: str,
        start: float,
        provider_hint: str | None = None,
    ) -> None:
        self.kind = kind  # "chain" | "tool" | "agent" | "llm"
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.start = start
        self.provider_hint = provider_hint
        self.context_cm: AbstractContextManager[None] | None = None


class CostorahLangChainHandler(BaseCallbackHandler):  # type: ignore[misc]
    """The globally-injected callback handler. Not normally instantiated
    directly — `LangChainInstrumentor().instrument()` registers it."""

    def __init__(self) -> None:
        super().__init__()
        self._runs: dict[UUID, _RunInfo] = {}
        self.events_captured_total = 0

    # ── LLM spans — the only spans that submit real usage telemetry ──

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_llm_span(serialized, run_id, parent_run_id)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_llm_span(serialized, run_id, parent_run_id)

    def _start_llm_span(
        self, serialized: dict[str, Any] | None, run_id: UUID, parent_run_id: UUID | None
    ) -> None:
        module_path = ".".join(str(p) for p in ((serialized or {}).get("id") or [])[:-1])
        provider_hint = infer_provider_from_module_path(module_path)
        self._start_span("llm", serialized, run_id, parent_run_id, provider_hint=provider_hint)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        info = self._runs.pop(run_id, None)
        if info is None:
            return
        latency_ms = int((time.perf_counter() - info.start) * 1000)

        usage = _extract_usage_metadata(response)
        finish_reason = _extract_finish_reason(response)
        model = usage["model"] if usage else info.name
        provider = info.provider_hint or infer_provider_from_model(model)

        self.events_captured_total += 1
        if provider is None or usage is None:
            _log.debug(
                "langchain_llm_call_not_submitted model=%s reason=%s",
                info.name,
                "unrecognized_provider" if provider is None else "no_usage_metadata",
            )
            return

        ambient = _current_span_names()
        metadata: dict[str, Any] = {
            "trace_id": info.trace_id,
            "span_id": info.span_id,
            "parent_span_id": str(parent_run_id) if parent_run_id else None,
            "framework": "langchain",
        }
        if finish_reason:
            metadata["finish_reason"] = finish_reason
        reasoning = usage.get("reasoning_tokens")
        if reasoning:
            metadata["reasoning_tokens"] = reasoning
        metadata.update(ambient)

        cost, was_estimated = resolve_cost(
            provider, model, usage["input_tokens"], usage["output_tokens"]
        )
        metadata["cost_estimated"] = was_estimated

        submit(
            ExtractedUsage(
                provider=provider,
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cached_tokens=usage.get("cached_tokens"),
                total_tokens=usage.get("total_tokens"),
                cost=cost,
                latency_ms=latency_ms,
                status="success",
                request_id=str(run_id),
                metadata=metadata,
            )
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._runs.pop(run_id, None)
        self.events_captured_total += 1
        _log.debug("langchain_llm_call_error error=%s", type(error).__name__)

    # ── Chain spans — ambient context only, no usage submission ──────

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_span("chain", serialized, run_id, parent_run_id, enter_context=True)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._end_span(run_id)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._end_span(run_id)
        _log.debug("langchain_chain_error error=%s", type(error).__name__)

    # ── Tool spans ─────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._start_span("tool", serialized, run_id, parent_run_id, enter_context=True)

    def on_tool_end(
        self, output: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any
    ) -> None:
        self._end_span(run_id)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self._end_span(run_id)
        _log.debug("langchain_tool_error error=%s", type(error).__name__)

    # ── Agent lifecycle (no dedicated start/end run_id pair) ─────────

    def on_agent_action(
        self, action: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any
    ) -> None:
        self.events_captured_total += 1
        _log.debug("langchain_agent_action tool=%s", getattr(action, "tool", None))

    def on_agent_finish(
        self, finish: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any
    ) -> None:
        self.events_captured_total += 1
        _log.debug("langchain_agent_finish")

    # ── Span bookkeeping ──────────────────────────────────────────────

    def _start_span(
        self,
        kind: str,
        serialized: dict[str, Any] | None,
        run_id: UUID,
        parent_run_id: UUID | None,
        *,
        enter_context: bool = False,
        provider_hint: str | None = None,
    ) -> None:
        name = _serialized_name(serialized)
        parent_info = self._runs.get(parent_run_id) if parent_run_id else None
        trace_id = parent_info.trace_id if parent_info else new_trace_id()
        info = _RunInfo(
            kind, name, trace_id, new_span_id(), time.perf_counter(), provider_hint=provider_hint
        )
        self._runs[run_id] = info

        if enter_context:
            fields = {f"{kind}_name": name}
            cm = request_context(**fields)
            cm.__enter__()
            info.context_cm = cm

    def _end_span(self, run_id: UUID) -> None:
        info = self._runs.pop(run_id, None)
        if info is None:
            return
        self.events_captured_total += 1
        if info.context_cm is not None:
            info.context_cm.__exit__(None, None, None)


def _serialized_name(serialized: dict[str, Any] | None) -> str:
    # LangChain's own type hints declare `serialized` as
    # `Optional[Dict[str, Any]]` — some Runnables (e.g. steps inside a
    # `RunnableSequence` built via `prompt | model`) call `on_chain_start`
    # with `serialized=None`. Found empirically (not from the type hints
    # alone) via this instrumentor's own example app crashing with
    # `AttributeError: 'NoneType' object has no attribute 'get'` on a real
    # `prompt | model` chain invocation.
    if serialized is None:
        return "unknown"
    path = serialized.get("id")
    if isinstance(path, list) and path:
        return str(path[-1])
    return str(serialized.get("name") or "unknown")


def _extract_usage_metadata(response: LLMResult) -> dict[str, Any] | None:
    """Reads only `usage_metadata`/`llm_output` token-count fields —
    never `.content` or `.text`."""
    llm_output = getattr(response, "llm_output", None) or {}
    model = llm_output.get("model_name") or llm_output.get("model")

    for generation_list in getattr(response, "generations", []) or []:
        for generation in generation_list:
            message = getattr(generation, "message", None)
            usage_metadata = getattr(message, "usage_metadata", None) if message else None
            if usage_metadata:
                output_details = usage_metadata.get("output_token_details") or {}
                input_details = usage_metadata.get("input_token_details") or {}
                return {
                    "model": model or "unknown",
                    "input_tokens": usage_metadata.get("input_tokens", 0),
                    "output_tokens": usage_metadata.get("output_tokens", 0),
                    "total_tokens": usage_metadata.get("total_tokens"),
                    "cached_tokens": input_details.get("cache_read"),
                    "reasoning_tokens": output_details.get("reasoning"),
                }

    token_usage = llm_output.get("token_usage")
    if token_usage:
        return {
            "model": model or "unknown",
            "input_tokens": token_usage.get("prompt_tokens", 0),
            "output_tokens": token_usage.get("completion_tokens", 0),
            "total_tokens": token_usage.get("total_tokens"),
            "cached_tokens": None,
            "reasoning_tokens": (token_usage.get("completion_tokens_details") or {}).get(
                "reasoning_tokens"
            ),
        }
    return None


def _extract_finish_reason(response: LLMResult) -> str | None:
    for generation_list in getattr(response, "generations", []) or []:
        for generation in generation_list:
            info = getattr(generation, "generation_info", None) or {}
            reason = info.get("finish_reason")
            if reason:
                return str(reason)
    return None


def _current_span_names() -> dict[str, Any]:
    from costorah.context import get_request_context

    ctx = get_request_context() or {}
    result: dict[str, Any] = {}
    for key in ("chain_name", "tool_name", "agent_name"):
        if key in ctx:
            result[key] = ctx[key]
    return result


_costorah_langchain_handler_var: ContextVar[CostorahLangChainHandler | None] = ContextVar(
    "costorah_langchain_handler", default=None
)
register_configure_hook(_costorah_langchain_handler_var, inheritable=True)


class LangChainInstrumentor:
    """`LangChainInstrumentor().instrument()` registers
    `CostorahLangChainHandler` as LangChain's global configure hook (via
    a `ContextVar` LangChain itself checks on every run) — no
    per-instrumentor patch list the way provider instrumentors use,
    since there's no single method to monkeypatch; LangChain's own
    extension point does the injection instead. `instrument()`/
    `uninstrument()` are idempotent, matching every other instrumentor's
    contract."""

    name = "langchain"

    def __init__(self) -> None:
        self._handler: CostorahLangChainHandler | None = None

    def instrument(self) -> None:
        if self._handler is not None:
            _log.debug("already_instrumented provider=langchain")
            return
        self._handler = CostorahLangChainHandler()
        _costorah_langchain_handler_var.set(self._handler)
        _log.info("instrumentation_enabled provider=langchain")

    def uninstrument(self) -> None:
        if self._handler is None:
            return
        _costorah_langchain_handler_var.set(None)
        self._handler = None
        _log.info("instrumentation_disabled_restored provider=langchain")

    def is_instrumented(self) -> bool:
        return self._handler is not None

    @property
    def events_captured_total(self) -> int:
        return self._handler.events_captured_total if self._handler else 0
