"""
BaseInstrumentor — the plugin interface every provider auto-instrumentor
implements, mirroring the Monitoring Agent's `BaseCollector` design
(EP-17, `monitoring-agent/costorah_agent/collectors/base.py`) so the whole
COSTORAH ecosystem shares one extensibility pattern: implement a handful
of lifecycle methods, register it, and the rest of the system never needs
provider-specific logic.

Lifecycle
---------
    __init__(...)               — cheap, no I/O, no patching yet
    instrument()                 — apply monkey patches; idempotent
    uninstrument()                — restore original methods; idempotent
    is_instrumented()             — current patch state
    extract_usage(response)       — pull raw usage fields out of a
                                     provider-native response object
    normalize(raw_usage, ...)     — build a costorah ExtractedUsage from
                                     what extract_usage() returned

extract_usage() and normalize() are pure/no-I/O so each provider's
response-parsing logic is independently unit-testable against a fixture
response object (real or a minimal stand-in), without instrumenting
anything or making a network call — exactly how EP-17's collectors keep
normalize() separately testable from collect().
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from costorah._logging import get_logger
from costorah.types import UsageStatus

_log = get_logger(__name__)


class InstrumentationError(Exception):
    """Raised for a genuine instrumentation setup/teardown failure (e.g.
    the target provider package isn't installed). Never raised for a
    single request's extraction/submission failure — those are logged and
    swallowed so instrumentation can never break the caller's own request
    (see `_submission.py`)."""


@dataclass(slots=True)
class ExtractedUsage:
    """The common currency every instrumentor produces, regardless of
    provider — deliberately field-for-field identical to EP-16's
    `IngestUsageRequest` (like the Monitoring Agent's
    `NormalizedUsageEvent`), so submission is a direct pass-through with
    no translation step."""

    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int | None = None
    total_tokens: int | None = None
    cost: float = 0.0
    currency: str = "USD"
    latency_ms: int | None = None
    status: UsageStatus = "success"
    request_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


class _PatchRecord:
    """Tracks one monkey-patched attribute so it can be restored exactly."""

    __slots__ = ("attr", "original", "target")

    def __init__(self, target: type, attr: str, original: Any) -> None:
        self.target = target
        self.attr = attr
        self.original = original


class BaseInstrumentor(ABC):
    """Common interface every provider auto-instrumentor implements.

    Thread safety: `instrument()`/`uninstrument()` are guarded by a lock
    so concurrent calls from multiple threads can't leave the patch state
    half-applied; the patched methods themselves only read `self` (the
    instrumentor instance) inside the wrapper closure, never mutate
    shared state, so instrumented calls are as thread-safe as the
    provider SDK's own methods already are.
    """

    #: Provider slug — must be one of costorah.types.SUPPORTED_PROVIDERS.
    name: str = "base"

    def __init__(
        self,
        *,
        enabled: bool = True,
        capture_metadata: bool = True,
        calculate_cost: bool = True,
        client: Any = None,
    ) -> None:
        self.enabled = enabled
        self.capture_metadata = capture_metadata
        self.calculate_cost_enabled = calculate_cost
        self._client = client
        # Subclasses that don't own their own patch application (e.g. the
        # OpenAI-family instrumentors sharing one reference-counted patch,
        # see _openai_compatible.py) may append a non-_PatchRecord truthy
        # marker instead — is_instrumented() only checks non-emptiness.
        self._patches: list[Any] = []
        self._lock = threading.Lock()
        self._events_captured_total = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    def instrument(self) -> None:
        """Apply monkey patches. Idempotent — calling twice is a no-op
        (logged, not raised), matching `costorah-agent`'s and every
        reference APM SDK's "double instrument is safe" contract."""
        if not self.enabled:
            _log.info("instrumentation_disabled provider=%s", self.name)
            return
        with self._lock:
            if self._patches:
                _log.debug("already_instrumented provider=%s", self.name)
                return
            self._apply_patches()
            _log.info("instrumentation_enabled provider=%s", self.name)

    def uninstrument(self) -> None:
        """Restore original SDK methods exactly. Idempotent."""
        with self._lock:
            if not self._patches:
                return
            for record in reversed(self._patches):
                setattr(record.target, record.attr, record.original)
            self._patches.clear()
            _log.info("instrumentation_disabled_restored provider=%s", self.name)

    def is_instrumented(self) -> bool:
        with self._lock:
            return len(self._patches) > 0

    # ── Patch bookkeeping (used by subclasses) ──────────────────────

    def _patch(self, target: type, attr: str, replacement: Any) -> None:
        """Record + apply one monkey patch. Only call this from within
        `_apply_patches()` (already under `self._lock`)."""
        original = target.__dict__.get(attr)
        if original is None:
            # Fall back to getattr for inherited methods not defined
            # directly on `target` — still safe to restore via setattr,
            # which will shadow the inherited method the same way.
            original = getattr(target, attr)
        self._patches.append(_PatchRecord(target, attr, original))
        setattr(target, attr, replacement)

    @abstractmethod
    def _apply_patches(self) -> None:
        """Subclasses: call `self._patch(...)` for every method this
        instrumentor wraps. Must raise `InstrumentationError` (not a bare
        ImportError/AttributeError) if the target SDK isn't
        installed/compatible."""

    # ── Extraction / normalization (pure, no I/O) ────────────────────

    @abstractmethod
    def extract_usage(self, response: Any) -> dict[str, Any]:
        """Pull raw usage fields out of a provider-native response
        object. Returns a provider-shaped dict (NOT yet normalized) —
        kept separate from normalize() so each step is independently
        testable against a fixture response."""

    @abstractmethod
    def normalize(
        self,
        raw_usage: dict[str, Any],
        *,
        model: str,
        latency_ms: int,
        status: UsageStatus,
        request_id: str | None = None,
    ) -> ExtractedUsage:
        """Convert extract_usage()'s output into a common ExtractedUsage.
        Pure function, no I/O."""

    # ── Shared timing helper for subclasses ──────────────────────────

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    def _record_captured(self, count: int = 1) -> None:
        self._events_captured_total += count

    @property
    def events_captured_total(self) -> int:
        return self._events_captured_total
