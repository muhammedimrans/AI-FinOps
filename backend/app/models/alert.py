"""
Alert engine ORM models — EP-19.3.

Four tables, all additive (no existing table is modified by this module):

  AlertRule        — organization-configurable threshold rules (today: only
                      budget_threshold/budget_exceeded are threshold-style
                      alert types with a numeric condition to configure; see
                      docs/realtime/ALERT_ARCHITECTURE.md for why the other
                      16 ticket-named alert types are event-triggered
                      instead of rule-evaluated).
  Alert             — one fired alert instance/occurrence, with dedup and
                      acknowledge/resolve/dismiss lifecycle state.
  AlertPreference   — per-user, per-organization notification preferences.
  AlertSuppression  — temporary suppression windows (maintenance, per-org,
                      per-provider, per-alert-type).

External IDs, timestamps, and soft-delete all come from BaseModel — no
model here re-declares them.
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class AlertType(enum.StrEnum):
    """Every alert type named in the EP-19.3 ticket. Not all are wired to a
    real trigger today — see ALERT_ARCHITECTURE.md's honest accounting,
    same discipline as EP-19.1's EventType. A value outside this set must
    never crash a consumer; treat it as open, not closed."""

    BUDGET_THRESHOLD = "budget_threshold"
    BUDGET_EXCEEDED = "budget_exceeded"
    DAILY_SPEND_SPIKE = "daily_spend_spike"
    HOURLY_SPEND_SPIKE = "hourly_spend_spike"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_RECOVERY = "provider_recovery"
    SDK_OFFLINE = "sdk_offline"
    SDK_RECONNECTED = "sdk_reconnected"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    API_KEY_EXPIRED = "api_key_expired"
    ORG_MEMBER_ADDED = "org_member_added"
    ORG_MEMBER_REMOVED = "org_member_removed"
    HIGH_LATENCY = "high_latency"
    RATE_LIMIT_SPIKE = "rate_limit_spike"
    LARGE_COST_INCREASE = "large_cost_increase"
    USAGE_INGESTION_FAILURE = "usage_ingestion_failure"
    WEBHOOK_DELIVERY_FAILURE = "webhook_delivery_failure"


class AlertSeverity(enum.StrEnum):
    """Ordered low → high; `severity_rank()` gives the numeric ordering used
    for sorting and preference threshold comparisons."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_SEVERITY_RANK: dict[AlertSeverity, int] = {
    AlertSeverity.INFO: 0,
    AlertSeverity.LOW: 1,
    AlertSeverity.MEDIUM: 2,
    AlertSeverity.HIGH: 3,
    AlertSeverity.CRITICAL: 4,
}


def severity_rank(severity: AlertSeverity) -> int:
    return _SEVERITY_RANK[severity]


class AlertStatus(enum.StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertOperator(enum.StrEnum):
    """Comparison operators a threshold-style AlertRule can use. `pct_increase`
    and `rolling_average` are evaluated by the caller supplying an
    already-computed percentage/average as `current_value` — the operator
    itself is still a plain numeric comparison against `threshold` once that
    value is computed; see app/alerts/conditions.py."""

    GT = "gt"
    LT = "lt"
    EQ = "eq"
    GTE = "gte"
    LTE = "lte"


class SuppressionScope(enum.StrEnum):
    ORGANIZATION = "organization"
    PROVIDER = "provider"
    ALERT_TYPE = "alert_type"


def _alert_enum(name: str, enum_cls: type[enum.StrEnum]) -> SQLEnum:
    return SQLEnum(
        enum_cls, name=name, create_type=True, values_callable=lambda e: [m.value for m in e]
    )


class AlertRule(BaseModel):
    """A user-configurable threshold rule. Only `budget_threshold` and
    `budget_exceeded` are evaluated against real data today (see
    app/alerts/rule_engine.py + the ingestion hook in app/api/v1/ingest.py);
    a rule for any other AlertType can be created and stored but nothing
    currently evaluates it, which is stated rather than hidden.

    External ID prefix: ``alrule_``
    """

    __tablename__ = "alert_rules"
    _external_id_prefix = "alrule"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE", name="fk_alert_rules_organization_id"),
        nullable=False,
        index=False,
    )
    alert_type: Mapped[AlertType] = mapped_column(
        _alert_enum("alert_type", AlertType), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        _alert_enum("alert_severity", AlertSeverity),
        nullable=False,
        default=AlertSeverity.MEDIUM,
        server_default=AlertSeverity.MEDIUM.value,
    )
    operator: Mapped[AlertOperator] = mapped_column(
        _alert_enum("alert_operator", AlertOperator), nullable=False
    )
    threshold: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=6), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_alert_rules_created_by"),
        nullable=True,
        default=None,
    )

    organization: Mapped[Organization] = relationship("Organization", lazy="raise")

    __table_args__ = (
        Index("ix_alert_rules_org_id", "organization_id"),
        Index("ix_alert_rules_org_type", "organization_id", "alert_type"),
        Index("ix_alert_rules_org_enabled", "organization_id", "enabled"),
    )


class Alert(BaseModel):
    """One fired alert. `dedup_key` groups repeated occurrences of "the same
    underlying condition" (e.g. the same provider repeatedly failing) into
    one row with an incrementing `occurrence_count`, rather than one row per
    occurrence — see app/alerts/dedup.py.

    External ID prefix: ``alert_``
    """

    __tablename__ = "alerts"
    _external_id_prefix = "alert"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE", name="fk_alerts_organization_id"),
        nullable=False,
        index=False,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("alert_rules.id", ondelete="SET NULL", name="fk_alerts_rule_id"),
        nullable=True,
        default=None,
    )
    alert_type: Mapped[AlertType] = mapped_column(
        _alert_enum("alert_type", AlertType), nullable=False
    )
    severity: Mapped[AlertSeverity] = mapped_column(
        _alert_enum("alert_severity", AlertSeverity), nullable=False
    )
    status: Mapped[AlertStatus] = mapped_column(
        _alert_enum("alert_status", AlertStatus),
        nullable=False,
        default=AlertStatus.OPEN,
        server_default=AlertStatus.OPEN.value,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment=(
            "Which subsystem fired this alert "
            "(ingestion, provider_test, membership, api_key, rule_engine)"
        ),
    )
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    alert_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="Never store secrets here — provider names, amounts, ids only.",
    )
    first_occurred_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    last_occurred_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_alerts_acknowledged_by"),
        nullable=True,
        default=None,
    )
    acknowledged_at: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    acknowledgement_reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    resolved_at: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    dismissed_at: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    organization: Mapped[Organization] = relationship("Organization", lazy="raise")

    __table_args__ = (
        Index("ix_alerts_org_id", "organization_id"),
        Index("ix_alerts_org_status", "organization_id", "status"),
        Index("ix_alerts_org_type", "organization_id", "alert_type"),
        Index("ix_alerts_org_severity", "organization_id", "severity"),
        Index("ix_alerts_dedup_key", "organization_id", "dedup_key"),
    )


class AlertPreference(BaseModel):
    """Per-user, per-organization notification preferences. One row per
    (organization_id, user_id) — created lazily on first read with defaults
    rather than requiring an explicit setup step.

    External ID prefix: ``alpref_``
    """

    __tablename__ = "alert_preferences"
    _external_id_prefix = "alpref"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id", ondelete="CASCADE", name="fk_alert_preferences_organization_id"
        ),
        nullable=False,
        index=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_alert_preferences_user_id"),
        nullable=False,
        index=False,
    )
    enabled_alert_types: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
        comment="Empty list means all alert types are enabled.",
    )
    min_severity: Mapped[AlertSeverity] = mapped_column(
        _alert_enum("alert_severity_pref", AlertSeverity),
        nullable=False,
        default=AlertSeverity.INFO,
        server_default=AlertSeverity.INFO.value,
    )
    quiet_hours_start_minute: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="Minutes since midnight, in the user's timezone. NULL disables quiet hours.",
    )
    quiet_hours_end_minute: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default=text("'UTC'")
    )
    daily_digest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    immediate_notifications: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    max_notifications: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment=(
            "Retention cap — oldest notifications beyond this count are pruned. "
            "NULL = unbounded."
        ),
    )

    organization: Mapped[Organization] = relationship("Organization", lazy="raise")
    user: Mapped[User] = relationship("User", lazy="raise")

    __table_args__ = (
        Index(
            "uq_alert_preferences_org_user",
            "organization_id",
            "user_id",
            unique=True,
        ),
    )


class AlertSuppression(BaseModel):
    """A temporary suppression window. `target` is interpreted according to
    `scope`: NULL for ORGANIZATION scope, a provider slug for PROVIDER
    scope, an AlertType value for ALERT_TYPE scope. `ends_at=NULL` means the
    suppression stays active until explicitly cleared (e.g. an indefinite
    maintenance window).

    External ID prefix: ``alsup_``
    """

    __tablename__ = "alert_suppressions"
    _external_id_prefix = "alsup"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id", ondelete="CASCADE", name="fk_alert_suppressions_organization_id"
        ),
        nullable=False,
        index=False,
    )
    scope: Mapped[SuppressionScope] = mapped_column(
        _alert_enum("suppression_scope", SuppressionScope), nullable=False
    )
    target: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    starts_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[Any | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_alert_suppressions_created_by"),
        nullable=True,
        default=None,
    )

    organization: Mapped[Organization] = relationship("Organization", lazy="raise")

    __table_args__ = (
        Index("ix_alert_suppressions_org_id", "organization_id"),
        Index("ix_alert_suppressions_org_scope", "organization_id", "scope"),
    )
