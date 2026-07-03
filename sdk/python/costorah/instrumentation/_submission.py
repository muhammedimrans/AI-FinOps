"""
Submits an ExtractedUsage event to COSTORAH by reusing the EP-18.1
`Costorah` client's `track()` — no separate HTTP/auth/retry logic is
implemented here, per the ticket's "Reuse EP-18.1 SDK Core" directive.

Telemetry submission must never break the caller's actual AI request: any
failure (missing API key, network error, validation error, exhausted
retries) is logged and swallowed here, never raised into the instrumented
provider SDK call.

EP-18.4: if a framework integration (e.g. `costorah.integrations.fastapi`)
has set ambient request context (`costorah.context.request_context`), it's
merged into every event's `metadata["request_context"]` here — additive,
never overwriting metadata the caller already set.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from costorah._logging import get_logger
from costorah.context import get_request_context
from costorah.exceptions import CostorahError

if TYPE_CHECKING:
    from costorah.client import Costorah
    from costorah.instrumentation.base import ExtractedUsage

_log = get_logger(__name__)

_default_client: Costorah | None = None
_default_client_failed = False


def set_default_client(client: Costorah | None) -> None:
    """Sets (or clears, with None) the client instrumentation submits
    through when no explicit `client` is passed to an instrumentor —
    used by framework integrations to wire up auto-initialization from
    a single place (e.g. `CostorahMiddleware(client=...)`)."""
    global _default_client, _default_client_failed
    _default_client = client
    _default_client_failed = False


def _get_or_build_client(explicit_client: Costorah | None) -> Costorah | None:
    """Returns the client to submit through, or None if none is
    configured and no COSTORAH_API_KEY env var is set (logged once, not
    raised — instrumentation must degrade gracefully, not crash import)."""
    if explicit_client is not None:
        return explicit_client

    global _default_client, _default_client_failed
    if _default_client is not None:
        return _default_client
    if _default_client_failed:
        return None

    api_key = os.environ.get("COSTORAH_API_KEY")
    if not api_key:
        _default_client_failed = True
        _log.warning(
            "instrumentation_no_client_configured: no Costorah client was passed to the "
            "instrumentor and COSTORAH_API_KEY is not set — usage will be captured locally "
            "(events_captured_total) but not submitted"
        )
        return None

    from costorah.client import Costorah

    try:
        endpoint = os.environ.get("COSTORAH_ENDPOINT", "https://api.costorah.com")
        _default_client = Costorah(api_key=api_key, endpoint=endpoint)
        return _default_client
    except CostorahError as exc:
        _default_client_failed = True
        _log.warning("instrumentation_client_init_failed error=%s", exc)
        return None


def submit(usage: ExtractedUsage, *, client: Costorah | None = None) -> bool:
    """Best-effort submission. Returns True if the event was accepted by
    COSTORAH, False for any failure (already logged)."""
    resolved = _get_or_build_client(client)
    if resolved is None:
        return False

    metadata = usage.metadata
    context = get_request_context()
    if context:
        metadata = {**usage.metadata, "request_context": context}

    try:
        resolved.track(
            provider=usage.provider,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=usage.cached_tokens,
            total_tokens=usage.total_tokens,
            cost=usage.cost,
            currency=usage.currency,
            latency_ms=usage.latency_ms,
            status=usage.status,
            request_id=usage.request_id,
            timestamp=usage.timestamp,
            metadata=metadata,
        )
        return True
    except CostorahError as exc:
        _log.warning(
            "instrumentation_submission_failed provider=%s model=%s error=%s",
            usage.provider,
            usage.model,
            exc,
        )
        return False


def reset_default_client_for_tests() -> None:
    """Test-only helper — clears the lazily-built module-level singleton
    so each test starts from a clean slate."""
    global _default_client, _default_client_failed
    _default_client = None
    _default_client_failed = False
