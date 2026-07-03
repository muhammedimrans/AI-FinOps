"""
Shared helpers for AI framework instrumentors (EP-18.7 — LangChain,
CrewAI, MCP). Every AI framework integration needs the same three
things, so they live here once instead of being copy-pasted:

  - Trace/span ID generation (`new_trace_id`/`new_span_id`).
  - Provider inference from a model name or a framework's own class
    path, since a framework's LLM call is only submittable through
    `client.track()` if it resolves to one of
    `costorah.types.SUPPORTED_PROVIDERS` — that enum is closed (it
    mirrors EP-16's backend schema, which this EP does not modify), so
    "provider=langchain" or "provider=crewai" is never valid; the real
    underlying provider (openai, anthropic, ...) must be inferred.
  - `submit_llm_span()`, the one place framework instrumentors submit a
    real usage event — reusing `costorah.instrumentation._submission`
    (which reuses the full EP-18.3 reliability pipeline: queue, worker,
    retry, circuit breaker) and `costorah.instrumentation.pricing` for
    cost calculation exactly the way every provider instrumentor
    already does.

What this module deliberately does NOT provide: a way to submit a
"usage" event for something that isn't an LLM call (a chain step, a
tool invocation, an agent lifecycle event). COSTORAH's ingestion
endpoint (EP-16) only accepts LLM usage records shaped around
provider/model/tokens/cost — there is no trace/span ingestion endpoint,
and adding one is a backend change explicitly out of scope for this EP.
Framework instrumentors that want to attach agent/tool/chain context to
telemetry do so by setting *ambient request context*
(`costorah.context.request_context`, the same mechanism the framework
integrations from EP-18.4/18.5 use) around the span, so any real LLM
usage event captured inside that span inherits the context — see each
instrumentor's module docstring for specifics.
"""

from __future__ import annotations

import uuid

from costorah.instrumentation.pricing import calculate_cost
from costorah.types import SUPPORTED_PROVIDERS

# Longest-prefix-first isn't required here since these are disjoint
# substrings in practice, but the dict is ordered by specificity anyway
# for readability. Model-name-based inference is inherently best-effort
# — frameworks that let users bring an arbitrary LiteLLM-style model
# string (CrewAI, some LangChain integrations) don't guarantee a
# provider field at all.
_MODEL_PREFIX_TO_PROVIDER: tuple[tuple[str, str], ...] = (
    ("gpt-", "openai"),
    ("o1-", "openai"),
    ("o3-", "openai"),
    ("chatgpt-", "openai"),
    ("text-embedding-", "openai"),
    ("claude-", "anthropic"),
    ("gemini-", "google"),
    ("command-", "cohere"),
    ("mistral-", "mistral"),
    ("mixtral-", "mistral"),
    ("grok-", "grok"),
    ("azure/", "azure_openai"),
    ("bedrock/", "bedrock"),
    ("ollama/", "ollama"),
    ("openrouter/", "openrouter"),
)

# LangChain (and similar frameworks) identify a chat model by its
# fully-qualified class path, e.g. ["langchain_openai", "chat_models",
# "base", "ChatOpenAI"] — the module path's top-level package name maps
# directly to a provider in the common case.
_MODULE_PREFIX_TO_PROVIDER: tuple[tuple[str, str], ...] = (
    ("langchain_openai", "openai"),
    ("langchain_anthropic", "anthropic"),
    ("langchain_google", "google"),
    ("langchain_mistralai", "mistral"),
    ("langchain_cohere", "cohere"),
    ("langchain_community.chat_models.azure_openai", "azure_openai"),
    ("langchain_community.llms.ollama", "ollama"),
    ("langchain_aws", "bedrock"),
)


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex}"


def new_span_id() -> str:
    return f"span_{uuid.uuid4().hex}"


def infer_provider_from_model(model: str | None) -> str | None:
    """Best-effort: a model name -> a costorah.types.SUPPORTED_PROVIDERS
    entry, or None if it can't be confidently inferred (never guesses —
    an unrecognized model name means "don't submit a usage event",
    handled by each instrumentor's caller)."""
    if not model:
        return None
    lowered = model.lower()
    for prefix, provider in _MODEL_PREFIX_TO_PROVIDER:
        if lowered.startswith(prefix):
            return provider
    return None


def infer_provider_from_module_path(module_path: str | None) -> str | None:
    """Best-effort: a Python module path (e.g. from LangChain's
    `serialized["id"]`, joined with '.') -> a supported provider."""
    if not module_path:
        return None
    for prefix, provider in _MODULE_PREFIX_TO_PROVIDER:
        if module_path.startswith(prefix):
            return provider
    return None


def resolve_cost(
    provider: str, model: str, input_tokens: int, output_tokens: int
) -> tuple[float, bool]:
    """Thin re-export of `costorah.instrumentation.pricing.calculate_cost`
    so AI-framework instrumentors import one module for both provider
    inference and cost lookup. `provider` must already be a validated
    member of `SUPPORTED_PROVIDERS` — callers check
    `infer_provider_from_*` succeeded before calling this."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"resolve_cost called with unsupported provider {provider!r}")
    return calculate_cost(provider, model, input_tokens, output_tokens)
