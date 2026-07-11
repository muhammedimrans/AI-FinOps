"""PlaygroundExecution ORM model — EP-25.4 (AI Playground).

Stores prompt/response history for the AI Playground — the one genuinely
new table this EP introduces, because no existing table stores prompt or
response *text* (UsageEvent/UsageCostRecord store aggregate token/cost
numbers only, by design, across every prior EP). Every metric field here
(tokens, cost, latency) is a denormalized copy of the same values already
written to UsageEvent/UsageCostRecord for this same request — convenient
for the History panel to read without a join, never the source of truth
for Analytics/Budgets/Dashboard, which continue to read exclusively from
UsageCostRecord as they always have.

External ID prefix: ``pgexec_``
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class PlaygroundExecutionStatus(enum.StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PlaygroundExecution(BaseModel):
    """One prompt/response round-trip executed from the AI Playground.

    ``comparison_group_id`` is set (and shared across several rows) when the
    execution was part of a Comparison Mode run — the same prompt sent to
    several providers/models at once (EP-25.4 Part "Comparison Mode").
    ``None`` for a normal single-provider execution.
    """

    __tablename__ = "playground_executions"
    _external_id_prefix = "pgexec"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id", ondelete="CASCADE", name="fk_playground_executions_organization_id"
        ),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_playground_executions_user_id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL", name="fk_playground_executions_project_id"),
        nullable=True,
        default=None,
    )
    provider_connection_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "provider_connections.id",
            ondelete="CASCADE",
            name="fk_playground_executions_provider_connection_id",
        ),
        nullable=False,
    )
    usage_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "usage_events.id", ondelete="SET NULL", name="fk_playground_executions_usage_event_id"
        ),
        nullable=True,
        default=None,
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    temperature: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=2), nullable=True)
    top_p: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=2), nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=8), nullable=True, default=None
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    latency_ms: Mapped[float | None] = mapped_column(Numeric(precision=12, scale=2), nullable=True)

    status: Mapped[PlaygroundExecutionStatus] = mapped_column(
        SQLEnum(
            PlaygroundExecutionStatus,
            name="playground_execution_status",
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)

    comparison_group_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, default=None
    )

    execution_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_playground_executions_org_created", "organization_id", "created_at"),
        Index("ix_playground_executions_user_created", "user_id", "created_at"),
        Index("ix_playground_executions_comparison_group", "comparison_group_id"),
    )
