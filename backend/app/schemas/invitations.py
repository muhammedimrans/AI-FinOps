"""Schemas for the invitation endpoints (EP-24.6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CreateInvitationRequest(BaseModel):
    """Invite an email address to join an organization."""

    email: EmailStr
    role: str = "member"  # MembershipRole value


class InvitationResponse(BaseModel):
    """One invitation row."""

    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: str  # MembershipRole value
    # Derived at read time — "expired" is never a persisted status; a
    # PENDING row whose expires_at has passed is reported as "expired"
    # (see Invitation model's own docstring).
    status: str
    invited_by_name: str | None = None
    invited_by_email: str | None = None
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    cancelled_at: datetime | None = None


class InvitationsListResponse(BaseModel):
    """All pending invitations for an organization."""

    invitations: list[InvitationResponse]
    total: int


class InvitationPreview(BaseModel):
    """Non-sensitive details shown before an invitee accepts/declines —
    returned inline by the accept/decline endpoints on failure, and by
    every successful accept, so the frontend never needs a separate
    token-preview lookup."""

    organization_name: str
    role: str
    email: str
    expires_at: datetime


class AcceptInvitationResponse(BaseModel):
    """Result of a successful POST /v1/invitations/{token}/accept."""

    organization_id: uuid.UUID
    organization_name: str
    role: str


class TransferOwnershipRequest(BaseModel):
    """Transfer organization ownership to another member."""

    new_owner_membership_id: uuid.UUID


class MessageResponse(BaseModel):
    """Generic confirmation message (mirrors app.schemas.auth.MessageResponse)."""

    message: str = Field(..., min_length=1)
