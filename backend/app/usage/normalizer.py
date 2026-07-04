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

Supported providers (EP-08)
----------------------------
- OpenAI  — ``GET /v1/organization/usage/completions`` response items
- Anthropic — ``GET /v1/usage`` admin API response items
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
    return registry
