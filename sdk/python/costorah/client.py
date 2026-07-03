"""
Costorah — the SDK's public entry point.

    from costorah import Costorah

    client = Costorah(api_key="costorah_live_xxxxxxxxx")
    client.track(
        provider="openai",
        model="gpt-4.1",
        input_tokens=500,
        output_tokens=220,
        cost=0.041,
        latency_ms=621,
    )

Thread safety: a single `Costorah` instance is safe to share across
threads. `track()` makes one blocking HTTP call per invocation via an
underlying `httpx.Client`, which manages its own connection pool safely
across concurrent callers — there is no SDK-level mutable state shared
between calls beyond that pool.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from costorah._http import HttpTransport
from costorah._logging import get_logger
from costorah._util import generate_request_id
from costorah.config import Config
from costorah.exceptions import ValidationError
from costorah.types import SUPPORTED_PROVIDERS, UsageStatus

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TrackResult:
    """Result of a successful `track()` call."""

    success: bool
    usage_id: str
    request_id: str
    processed_at: str
    duplicate: bool


class Costorah:
    """The COSTORAH SDK client."""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = "https://api.costorah.com",
        timeout: float = 30.0,
        batch_size: int = 25,
        flush_interval: float = 5.0,
        max_retries: int = 3,
        verify_tls: bool = True,
        _transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = Config(
            api_key=api_key,
            endpoint=endpoint,
            timeout=timeout,
            batch_size=batch_size,
            flush_interval=flush_interval,
            max_retries=max_retries,
            verify_tls=verify_tls,
        )
        self._transport = HttpTransport(self.config, transport=_transport)

    def track(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int | None = None,
        total_tokens: int | None = None,
        cost: float = 0.0,
        currency: str = "USD",
        latency_ms: int | None = None,
        status: UsageStatus = "success",
        region: str | None = None,
        project_id: str | None = None,
        request_id: str | None = None,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TrackResult:
        """Manually report one usage event. See `sdk/shared/API_CONTRACT.md`
        for the exact field semantics — they match EP-16's ingestion API
        one-to-one. Raises a `costorah.*` exception on any failure; never
        returns a partial/ambiguous result."""
        payload = self._build_payload(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            total_tokens=total_tokens,
            cost=cost,
            currency=currency,
            latency_ms=latency_ms,
            status=status,
            region=region,
            project_id=project_id,
            request_id=request_id,
            timestamp=timestamp,
            metadata=metadata,
        )
        body = self._transport.post_usage_event(payload)
        return TrackResult(
            success=bool(body.get("success", True)),
            usage_id=str(body["usage_id"]),
            request_id=str(body["request_id"]),
            processed_at=str(body["processed_at"]),
            duplicate=bool(body.get("duplicate", False)),
        )

    def _build_payload(
        self,
        *,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int | None,
        total_tokens: int | None,
        cost: float,
        currency: str,
        latency_ms: int | None,
        status: UsageStatus,
        region: str | None,
        project_id: str | None,
        request_id: str | None,
        timestamp: datetime | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_provider = provider.strip().lower()
        if normalized_provider not in SUPPORTED_PROVIDERS:
            raise ValidationError(
                f"Unsupported provider {provider!r}. Must be one of: {sorted(SUPPORTED_PROVIDERS)}"
            )
        if not model or not model.strip():
            raise ValidationError("model must not be blank")
        if input_tokens < 0 or output_tokens < 0:
            raise ValidationError("input_tokens and output_tokens must be >= 0")
        if cost < 0:
            raise ValidationError("cost must be >= 0")
        if cached_tokens is not None and cached_tokens > input_tokens:
            raise ValidationError("cached_tokens must not exceed input_tokens")
        if total_tokens is not None and total_tokens != input_tokens + output_tokens:
            raise ValidationError(
                f"total_tokens ({total_tokens}) must equal "
                f"input_tokens + output_tokens ({input_tokens + output_tokens})"
            )

        payload: dict[str, Any] = {
            "provider": normalized_provider,
            "model": model.strip(),
            "request_id": request_id or generate_request_id(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "currency": currency,
            "status": status,
            "metadata": metadata or {},
        }
        if cached_tokens is not None:
            payload["cached_tokens"] = cached_tokens
        if total_tokens is not None:
            payload["total_tokens"] = total_tokens
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if region is not None:
            payload["region"] = region
        if project_id is not None:
            payload["project_id"] = project_id
        if timestamp is not None:
            payload["timestamp"] = timestamp.isoformat()
        return payload

    def close(self) -> None:
        """Release the underlying HTTP connection pool. Safe to call more
        than once."""
        self._transport.close()

    def __enter__(self) -> Costorah:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
