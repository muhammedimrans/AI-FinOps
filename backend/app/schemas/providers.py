"""Provider API request/response schemas — EP-07."""

from __future__ import annotations

from pydantic import BaseModel

from app.providers.models import ConnectionStatus, ModelMetadata


class TestConnectionResponse(BaseModel):
    """Response for POST /providers/{provider}/test."""

    model_config = {"frozen": True}

    provider: str
    status: ConnectionStatus
    auth_valid: bool


class ModelsResponse(BaseModel):
    """Response for GET /providers/{provider}/models."""

    model_config = {"frozen": True}

    provider: str
    models: list[ModelMetadata]
    count: int
