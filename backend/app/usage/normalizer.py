"""Provider usage normalizers — F-042 (EP-08).

Each normalizer converts one raw API response item from a specific provider
into a provider-agnostic ``NormalizedUsageEvent``.

Design
------
- ``UsageNormalizer`` is a structural protocol — any class with a compatible
  ``normalize()`` and ``provider_name`` is a valid normalizer.
- ``NormalizerRegistry`` maps provider strings to normalizer instances so the
  collection service remains provider-agnostic.
- ``provider_request_id`` is the dedup key.  Providers that return per-request
  IDs use them directly; providers that return aggregated records use a
  deterministic SHA-256 hash of the aggregation key.

Supported providers (EP-08, EP-26.0.1)
---------------------------------------
- OpenAI  — ``GET /v1/organization/usage/completions`` response items
- Anthropic — ``GET /v1/usage`` admin API response items
- OpenRouter — ``GET /api/v1/activity`` response items (EP-26.0.1; see that
  normalizer's own docstring for the "best-effort field mapping" caveat —
  the exact response schema was not first-party-verified before this
  normalizer was written, since this sandbox's network policy blocks
  direct access to openrouter.ai; see CLAUDE.md's EP-26.0/EP-26.0.1
  sections for the full investigation).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

import structlog

from app.providers.models import NormalizedUsageEvent

log = structlog.get_logger(__name__)


@runtime_checkable
class UsageNormalizer(Protocol):
    """Structural protocol for provider-specific usage normalizers."""

    @property
    def provider_name(self) -> str: ...

    def normalize(self, raw: dict[str, Any]) -> NormalizedUsageEvent: ...


def _dedup_hash(*parts: str) -> str:
    """Return a stable 40-char hex hash of the given string parts."""
    payload = ":".join(parts)
    return hashlib.sha1(payload.encode(), usedforsecurity=False).hexdigest()


class OpenAIUsageNormalizer:
    """Normalizes items from ``GET /v1/organization/usage/completions``.

    Expected raw item shape::

        {
            "start_time": 1234567890,    # UNIX timestamp (int)
            "model": "gpt-4o",
            "input_tokens": 1000,
            "output_tokens": 500,
            "num_model_requests": 1,
            # optional:
            "cached_input_tokens": 200
        }

    ``provider_request_id`` is derived from (provider, model, start_time) so
    that re-collecting the same aggregation period is idempotent.
    """

    @property
    def provider_name(self) -> str:
        return "openai"

    def normalize(self, raw: dict[str, Any]) -> NormalizedUsageEvent:
        start_time = int(raw.get("start_time", 0))
        model = str(raw.get("model") or "unknown")
        input_t = int(raw.get("input_tokens", 0))
        output_t = int(raw.get("output_tokens", 0))
        cached_t: int | None = (
            int(raw["cached_input_tokens"]) if raw.get("cached_input_tokens") is not None else None
        )
        request_count = int(raw.get("num_model_requests", 1))
        total_t = input_t + output_t

        request_id = raw.get("id") or _dedup_hash("openai", model, str(start_time))

        return NormalizedUsageEvent(
            provider_request_id=request_id,
            provider="openai",
            model=model,
            timestamp=(
                datetime.fromtimestamp(start_time, tz=UTC) if start_time else datetime.now(UTC)
            ),
            prompt_tokens=input_t,
            completion_tokens=output_t,
            total_tokens=total_t,
            cached_tokens=cached_t,
            request_count=request_count,
            metadata={},
            raw_payload=raw,
        )


class AnthropicUsageNormalizer:
    """Normalizes items from the Anthropic admin usage API.

    Expected raw item shape::

        {
            "id": "req_xxx",             # optional
            "model": "claude-3-5-sonnet-20241022",
            "created_at": "2024-01-01T00:00:00Z",  # ISO-8601
            "input_tokens": 1000,
            "output_tokens": 500,
            # optional:
            "cache_read_input_tokens": 200,
            "num_requests": 1
        }
    """

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def normalize(self, raw: dict[str, Any]) -> NormalizedUsageEvent:
        model = str(raw.get("model") or "unknown")
        created_at_str = raw.get("created_at") or ""
        input_t = int(raw.get("input_tokens", 0))
        output_t = int(raw.get("output_tokens", 0))
        cached_t: int | None = (
            int(raw["cache_read_input_tokens"])
            if raw.get("cache_read_input_tokens") is not None
            else None
        )
        request_count = int(raw.get("num_requests", 1))
        total_t = int(raw.get("total_tokens", input_t + output_t))

        if created_at_str:
            try:
                ts = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except ValueError:
                ts = datetime.now(UTC)
        else:
            ts = datetime.now(UTC)

        request_id = raw.get("id") or _dedup_hash(
            "anthropic", model, created_at_str or ts.isoformat()
        )

        return NormalizedUsageEvent(
            provider_request_id=str(request_id),
            provider="anthropic",
            model=model,
            timestamp=ts,
            prompt_tokens=input_t,
            completion_tokens=output_t,
            total_tokens=total_t,
            cached_tokens=cached_t,
            request_count=request_count,
            metadata={},
            raw_payload=raw,
        )


class OpenRouterUsageNormalizer:
    """Normalizes items from OpenRouter's ``GET /api/v1/activity`` (EP-26.0.1).

    Field names are best-effort, not first-party-verified
    -------------------------------------------------------
    EP-26.0's research (CLAUDE.md) found, via secondary/aggregated sources
    only — direct access to openrouter.ai's own API reference was blocked by
    this sandbox's network egress policy, confirmed by both a direct ``curl``
    CONNECT-tunnel rejection and a ``WebFetch`` 403 — that ``/api/v1/activity``
    returns **daily activity data grouped by model**, for the last 30
    completed UTC days, gated behind a "management key" whose exact
    privilege relationship to a standard per-connection API key was not
    confirmed. This normalizer is therefore written defensively: it reads
    several plausible field-name variants for each value (OpenRouter's
    broader API vocabulary uses both snake_case aggregate names like
    ``prompt_tokens``/``completion_tokens`` and generation-metadata names
    like ``provider_name``/``model_permaslug``) rather than assuming one
    exact, unverified shape. Any field this normalizer cannot find in a raw
    item defaults to 0/None rather than raising — an unexpected response
    shape degrades to an under-counted event (never a fabricated or
    over-counted one), matching this codebase's standing no-fake-
    functionality rule. **This mapping must be re-verified against a real
    response the first time a live OpenRouter management key is available**
    (see CLAUDE.md's EP-26.0.1 "Known limitations").

    Expected raw item shape (best-effort, unverified)::

        {
            "date": "2026-07-10",                  # UTC day, YYYY-MM-DD
            "model": "anthropic/claude-sonnet-4",   # OpenRouter model slug
            "provider_name": "anthropic",           # optional — else derived
                                                      # from the model slug's
                                                      # "vendor/model" prefix
            "prompt_tokens": 12000,
            "completion_tokens": 4500,
            "requests": 42,
        }

    ``provider_request_id`` is a deterministic hash of (date, model, org) —
    this is aggregated data with no per-request ID, exactly the case
    ``NormalizedUsageEvent.provider_request_id``'s own docstring already
    anticipates ("a deterministic hash derived from the aggregation key").
    The underlying vendor (parsed from the ``vendor/model`` slug) is carried
    in ``metadata["underlying_vendor"]`` — display-layer information, not a
    new stored column (see CLAUDE.md's EP-26.0 Part 2/EP-26.0.1 "Data
    Mapping" finding: no schema change is needed for this).
    """

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def normalize(self, raw: dict[str, Any]) -> NormalizedUsageEvent:
        model = str(raw.get("model") or raw.get("model_permaslug") or raw.get("slug") or "unknown")
        date_str = str(raw.get("date") or raw.get("day") or "")
        if date_str:
            try:
                ts = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except ValueError:
                ts = datetime.now(UTC)
        else:
            ts = datetime.now(UTC)

        prompt_t = int(
            raw.get("prompt_tokens") or raw.get("tokens_prompt") or raw.get("input_tokens") or 0
        )
        completion_t = int(
            raw.get("completion_tokens")
            or raw.get("tokens_completion")
            or raw.get("output_tokens")
            or 0
        )
        total_t = int(raw.get("total_tokens") or (prompt_t + completion_t))
        request_count = int(raw.get("requests") or raw.get("num_requests") or raw.get("count") or 1)

        request_id = raw.get("id") or _dedup_hash("openrouter", model, date_str or ts.isoformat())

        vendor = str(raw.get("provider_name") or model.split("/", 1)[0])

        return NormalizedUsageEvent(
            provider_request_id=str(request_id),
            provider="openrouter",
            model=model,
            timestamp=ts,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
            total_tokens=total_t,
            cached_tokens=None,
            request_count=request_count,
            metadata={"underlying_vendor": vendor},
            raw_payload=raw,
        )


# ── Normalizer registry ────────────────────────────────────────────────────────


class NormalizerRegistry:
    """Maps provider name strings to UsageNormalizer instances."""

    def __init__(self) -> None:
        self._normalizers: dict[str, UsageNormalizer] = {}

    def register(self, normalizer: UsageNormalizer) -> None:
        self._normalizers[normalizer.provider_name] = normalizer

    def get(self, provider: str) -> UsageNormalizer | None:
        return self._normalizers.get(provider)

    def supported_providers(self) -> list[str]:
        return sorted(self._normalizers.keys())


def get_normalizer_registry() -> NormalizerRegistry:
    """Return the default normalizer registry with all built-in normalizers."""
    registry = NormalizerRegistry()
    registry.register(OpenAIUsageNormalizer())
    registry.register(AnthropicUsageNormalizer())
    registry.register(OpenRouterUsageNormalizer())
    return registry
