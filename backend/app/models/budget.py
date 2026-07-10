"""
Budget ORM model — EP-24.2.

A `Budget` is an organization-configured spending ceiling scoped to one of
four dimensions (organization/project/provider/model), evaluated on a
recurring period (daily/weekly/monthly/yearly/custom). It intentionally
carries no aggregation logic of its own — spend for a budget's scope+period
is always computed by `UsageCostRecordRepository`'s existing dimension-
filtered totals (see app/budgets/service.py), never a second query path.

This is additive alongside the pre-existing `Project.budget` column
(EP-19.3) and `app/api/v1/ingest.py`'s `_check_budget_alerts` ingest-time
check — both are left untouched. See CLAUDE.md's EP-24.2 section for why
they coexist rather than being migrated into this table.
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization


class BudgetScopeType(enum.StrEnum):
    """What dimension a budget's amount applies to. ORGANIZATION has no
    further qualifier; PROJECT/PROVIDER/MODEL each use exactly one of the
    scope_* columns below (enforced at the service layer, not the DB, to
    avoid a CHECK constraint per-dialect quirk)."""

    ORGANIZATION = "organization"
    PROJECT = "project"
    PROVIDER = "provider"
    MODEL = "model"


class BudgetPeriod(enum.StrEnum):
    """How often a budget's spend window resets. CUSTOM uses the explicit
    custom_period_start/custom_period_end columns; every other period is
    computed deterministically from "now" at evaluation time (see
    app/budgets/period.py) — no stored period boundaries needed for them."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"


def _budget_enum(name: str, enum_cls: type[enum.StrEnum]) -> SQLEnum:
    return SQLEnum(
        enum_cls, name=name, create_type=True, values_callable=lambda e: [m.value for m in e]
    )


class Budget(BaseModel):
    """
    An organization's configured spending ceiling for one scope+period.

    `threshold_percentages` is a JSONB list of numbers (e.g. [50, 75, 90,
    100, 110]) — each is evaluated independently every time this budget is
    checked (see app/budgets/service.py's BudgetEvaluationService), firing
    at most one Alert occurrence per (budget, period, threshold) via a
    dedicated dedup scope (app/alerts/dedup.py's budget_threshold_scope).

    External ID prefix: ``budget_``
    """

    __tablename__ = "budgets"
    _external_id_prefix = "budget"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE", name="fk_budgets_organization_id"),
        nullable=False,
        index=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_type: Mapped[BudgetScopeType] = mapped_column(
        _budget_enum("budget_scope_type", BudgetScopeType), nullable=False
    )
    # Exactly one of these three is populated, matching scope_type — never a
    # foreign key for provider/model, since neither has a catalog table
    # (both are free-text columns on UsageCostRecord itself; see
    # app/repositories/usage_cost_record_repository.py's _dimension_filters).
    scope_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_budgets_scope_project_id"),
        nullable=True,
        default=None,
    )
    scope_provider: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    scope_model: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)

    amount: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="USD", server_default=text("'USD'")
    )
    period: Mapped[BudgetPeriod] = mapped_column(
        _budget_enum("budget_period", BudgetPeriod), nullable=False
    )
    custom_period_start: Mapped[Any | None] = mapped_column(Date, nullable=True, default=None)
    custom_period_end: Mapped[Any | None] = mapped_column(Date, nullable=True, default=None)

    threshold_percentages: Mapped[list[float]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: [50.0, 75.0, 90.0, 100.0],
        server_default=text("'[50, 75, 90, 100]'::jsonb"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_budgets_created_by"),
        nullable=True,
        default=None,
    )

    organization: Mapped[Organization] = relationship("Organization", lazy="raise")

    __table_args__ = (
        Index("ix_budgets_org_id", "organization_id"),
        Index("ix_budgets_org_enabled", "organization_id", "enabled"),
        Index("ix_budgets_org_scope_type", "organization_id", "scope_type"),
        Index("ix_budgets_scope_project_id", "scope_project_id"),
    )
