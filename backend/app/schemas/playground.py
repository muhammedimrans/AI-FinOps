"""Request/response schemas for /v1/organizations/{org_id}/playground (EP-25.4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ExecutePlaygroundRequest(BaseModel):
    """Send one prompt to one connected provider."""

    provider_connection_id: uuid.UUID
    model_id: str = Field(min_length=1, max_length=255)
    project_id: uuid.UUID | None = None
    system_prompt: str | None = Field(default=None, max_length=32000)
    user_prompt: str = Field(min_length=1, max_length=32000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0, le=32000)


class ComparePlaygroundRequest(BaseModel):
    """Send the same prompt to several connections at once (Comparison Mode)."""

    targets: list[uuid.UUID] = Field(min_length=1, max_length=8)
    """One entry per ``provider_connection_id`` to compare — each uses its
    connection's own currently-selected model (set via a matching
    ``model_ids`` entry) rather than one shared model_id, since comparing
    "GPT-4o vs. Claude Sonnet vs. Gemini Pro" is the whole point of this
    mode."""
    model_ids: dict[str, str]
    """Keyed by the string form of each ``provider_connection_id`` in
    ``targets`` — which model to use for that specific connection."""
    project_id: uuid.UUID | None = None
    system_prompt: str | None = Field(default=None, max_length=32000)
    user_prompt: str = Field(min_length=1, max_length=32000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0, le=32000)


class PlaygroundExecutionResponse(BaseModel):
    id: uuid.UUID
    provider: str
    model: str
    provider_connection_id: uuid.UUID
    project_id: uuid.UUID | None
    system_prompt: str | None
    user_prompt: str
    response_text: str | None
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: Decimal | None
    currency: str
    latency_ms: float | None
    status: str
    error_message: str | None
    comparison_group_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaygroundHistoryResponse(BaseModel):
    executions: list[PlaygroundExecutionResponse]
    total: int


class ComparePlaygroundResponse(BaseModel):
    comparison_group_id: uuid.UUID
    executions: list[PlaygroundExecutionResponse]


class PlaygroundModelInfo(BaseModel):
    """One model available on a connection's live catalog, with the
    capability/pricing metadata Playground Insights displays (Part
    "Playground Insights") — reuses ModelMetadata exactly, no second catalog."""

    id: str
    display_name: str
    context_window: int | None
    max_output_tokens: int | None
    capabilities: list[str]
    input_cost_per_1k: float | None
    output_cost_per_1k: float | None
    is_deprecated: bool


class PlaygroundConnectionOption(BaseModel):
    """One provider connection eligible for use in the Playground —
    reused directly from ProviderConnection, not a second connection concept."""

    id: uuid.UUID
    provider_type: str
    display_name: str
    is_active: bool
    has_credential: bool
    last_validation_status: str | None


class PlaygroundConnectionsResponse(BaseModel):
    connections: list[PlaygroundConnectionOption]
