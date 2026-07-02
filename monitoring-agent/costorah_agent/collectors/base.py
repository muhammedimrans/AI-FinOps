"""
BaseCollector — the plugin interface every usage source implements.

This is the extensibility point EP-17 is built around: a provider REST API
today, an OpenAI/Anthropic SDK instrumentation hook, a LangChain/LlamaIndex/
CrewAI/AutoGen callback, or an MCP server tomorrow — all of them are just
another BaseCollector subclass registered with the CollectorRegistry. The
agent's core loop (Agent, in agent.py) never has provider-specific logic;
it only ever calls this interface.

Lifecycle
---------
    __init__(config)              — cheap, no I/O
    await collect()                — one poll: return NormalizedUsageEvent(s)
                                      already normalized (see normalize())
    await health()                 — cheap status check, safe to call often
    await shutdown()               — release connections/resources

collect() is expected to call normalize() internally on whatever raw shape
the source returns — normalize() is exposed separately (not just inlined)
so it's independently unit-testable per provider without any network I/O.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from costorah_agent.collectors.models import CollectorHealth, NormalizedUsageEvent


class CollectorError(Exception):
    """Raised by a collector on an unrecoverable per-poll failure.

    Collectors should prefer returning an empty list + reporting the issue
    via health() over raising, so one misbehaving provider never stops the
    agent's collection loop for every other provider. Raise only when the
    caller (the collection loop) truly cannot proceed for this collector.
    """


class BaseCollector(ABC):
    """Common interface every provider/framework/integration collector implements."""

    #: Provider slug used as the `provider` field on every event this
    #: collector produces, and as its registry key. Must match a value the
    #: EP-16 ingestion catalog recognizes (openai, anthropic, google,
    #: azure_openai, grok, openrouter, ollama, cohere, bedrock, mistral).
    name: str = "base"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._events_collected_total = 0

    @abstractmethod
    async def collect(self) -> list[NormalizedUsageEvent]:
        """
        Poll the source once and return newly observed usage, already
        normalized. Must not raise for "no new data" — return [] instead.
        Only raise CollectorError for a genuine per-poll failure the agent
        should log and back off from.
        """

    @abstractmethod
    def normalize(self, raw: Any) -> NormalizedUsageEvent:
        """
        Convert one provider-native record into a NormalizedUsageEvent.

        Pure function, no I/O — this is what makes normalization
        independently testable against fixture payloads without hitting a
        real API.
        """

    @abstractmethod
    async def health(self) -> CollectorHealth:
        """Return this collector's current status. Must not raise."""

    async def shutdown(self) -> None:
        """Release any held resources (HTTP clients, file handles, etc.).

        Default no-op — override if the collector holds anything that
        needs explicit cleanup. Must not raise.
        """
        return None

    def _record_collected(self, count: int) -> None:
        self._events_collected_total += count
