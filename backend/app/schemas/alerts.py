"""Request/response schemas for /v1/alerts (EP-19.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AlertResponse(BaseModel):
    """One fired alert instance, safe to return to a dashboard client."""

    id: uuid.UUID
    alert_type: str
    severity: str
    status: str
    title: str
    message: str
    source: str
    occurrence_count: int
    metadata: dict[str, Any]
    first_occurred_at: datetime
    last_occurred_at: datetime
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    acknowledgement_reason: str | None
    resolved_at: datetime | None
    dismissed_at: datetime | None
    created_at: datetime


class AlertsListResponse(BaseModel):
    alerts: list[AlertResponse]
    total: int


class AcknowledgeAlertRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class AlertPreferenceResponse(BaseModel):
    """A user's alert preferences for one organization. `enabled_alert_types`
    empty means "all types enabled" — see app/alerts/preferences.py."""

    enabled_alert_types: list[str]
    min_severity: str
    quiet_hours_start: str | None  # "HH:MM", derived from the stored minute-of-day
    quiet_hours_end: str | None
    timezone: str
    daily_digest: bool
    immediate_notifications: bool
    max_notifications: int | None


class UpdateAlertPreferenceRequest(BaseModel):
    enabled_alert_types: list[str] | None = None
    min_severity: str | None = None
    quiet_hours_start: str | None = None  # "HH:MM", or "" to clear
    quiet_hours_end: str | None = None
    timezone: str | None = None
    daily_digest: bool | None = None
    immediate_notifications: bool | None = None
    max_notifications: int | None = None


class CreateAlertRuleRequest(BaseModel):
    alert_type: str
    name: str = Field(min_length=1, max_length=255)
    severity: str = "medium"
    operator: str
    threshold: str  # decimal, as a string to avoid float precision issues
    enabled: bool = True


class UpdateAlertRuleRequest(BaseModel):
    """Partial update for an alert rule (EP-25.2 ownership-consistency audit).

    All fields optional — only supplied fields change. Added because
    ``AlertRule`` previously had create+delete but no edit, an asymmetry
    the audit's "if a user can create something they should also be able
    to edit/delete it" rule flags. Mirrors ``UpdateBudgetRequest``'s
    partial-update shape exactly.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    severity: str | None = None
    operator: str | None = None
    threshold: str | None = None
    enabled: bool | None = None


class AlertRuleResponse(BaseModel):
    id: uuid.UUID
    alert_type: str
    name: str
    severity: str
    operator: str
    threshold: str
    enabled: bool
    created_at: datetime


class AlertRulesListResponse(BaseModel):
    rules: list[AlertRuleResponse]
    total: int


class CreateAlertSuppressionRequest(BaseModel):
    scope: str
    target: str | None = None
    starts_at: datetime | None = None  # defaults to now
    ends_at: datetime | None = None  # None = indefinite
    reason: str | None = Field(default=None, max_length=2000)


class AlertSuppressionResponse(BaseModel):
    id: uuid.UUID
    scope: str
    target: str | None
    starts_at: datetime
    ends_at: datetime | None
    reason: str | None
    created_at: datetime


class AlertSuppressionsListResponse(BaseModel):
    suppressions: list[AlertSuppressionResponse]
    total: int
