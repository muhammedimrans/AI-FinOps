"""Request/response schemas for POST /v1/ingest/usage (EP-16)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.provider_connection import ProviderType

# Allow request timestamps up to this far into the future (clock drift),
# matching the tolerance EP-08's UsageEventValidator already uses.
_FUTURE_TOLERANCE_SECONDS = 300

# Serialized metadata larger than this is rejected outright — bounds both
# storage growth and the total request body size (EP-16's "reject oversized
# requests" requirement), without a separate raw-body-size middleware.
MAX_METADATA_BYTES = 16 * 1024

_SUPPORTED_PROVIDERS: frozenset[str] = frozenset(p.value for p in ProviderType)

UsageStatus = Literal["success", "error", "timeout", "cancelled"]


class IngestUsageRequest(BaseModel):
    """One usage record pushed by an authenticated integration."""

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=255)
    project_id: uuid.UUID | None = None
    request_id: str = Field(min_length=1, max_length=512)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)

    cost: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=8)

    latency_ms: int | None = Field(default=None, ge=0)
    status: UsageStatus = "success"
    region: str | None = Field(default=None, max_length=64)

    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider {value!r}. Must be one of: "
                f"{sorted(_SUPPORTED_PROVIDERS)}"
            )
        return normalized

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("model must not be blank")
        return stripped

    @field_validator("cost")
    @classmethod
    def _validate_cost_is_finite(cls, value: Decimal) -> Decimal:
        try:
            if not value.is_finite():
                raise ValueError("cost must be a finite number")
        except InvalidOperation as exc:
            raise ValueError("cost must be a valid decimal number") from exc
        return value

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.isalpha():
            raise ValueError("currency must be an alphabetic code (e.g. USD)")
        return normalized

    @field_validator("timestamp")
    @classmethod
    def _validate_timestamp_not_in_future(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        ts = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        future_limit = datetime.now(UTC) + timedelta(seconds=_FUTURE_TOLERANCE_SECONDS)
        if ts > future_limit:
            raise ValueError(f"timestamp {value!r} is too far in the future")
        return ts

    @model_validator(mode="after")
    def _validate_token_and_metadata(self) -> IngestUsageRequest:
        if self.total_tokens is not None:
            expected = self.input_tokens + self.output_tokens
            if self.total_tokens != expected:
                raise ValueError(
                    f"total_tokens ({self.total_tokens}) must equal "
                    f"input_tokens + output_tokens ({expected})"
                )
        if self.cached_tokens is not None and self.cached_tokens > self.input_tokens:
            raise ValueError("cached_tokens must not exceed input_tokens")

        try:
            metadata_size = len(json.dumps(self.metadata))
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must be JSON-serializable") from exc
        if metadata_size > MAX_METADATA_BYTES:
            raise ValueError(
                f"metadata is too large ({metadata_size} bytes; "
                f"max {MAX_METADATA_BYTES} bytes)"
            )
        return self

    @property
    def resolved_total_tokens(self) -> int:
        """total_tokens if given, else derived from input + output."""
        return (
            self.total_tokens
            if self.total_tokens is not None
            else self.input_tokens + self.output_tokens
        )

    @property
    def resolved_timestamp(self) -> datetime:
        """timestamp if given, else now — matches OpenAI/Datadog ingestion
        semantics where a real-time reporter can omit it entirely."""
        return self.timestamp if self.timestamp is not None else datetime.now(UTC)


class IngestUsageResponse(BaseModel):
    """Successful ingestion (new record or a resolved duplicate)."""

    success: bool = True
    usage_id: uuid.UUID
    request_id: str
    processed_at: datetime
    duplicate: bool
