"""EP-19.3: alert rule engine and notification persistence

Adds four new tables (alert_rules, alerts, alert_preferences,
alert_suppressions) following the standard BaseModel pattern (UUID v7
primary key, created_at/updated_at, deleted_at/deleted_by soft-delete,
cursor + deleted indexes).

Also extends two existing tables, additively only:
  - projects.budget            (nullable — no budget set by default)
  - provider_connections.health_status / last_failure_at /
    last_recovery_at / consecutive_failure_count (all nullable or
    zero-defaulted — every existing row degrades to "unknown, never
    checked" rather than a fabricated "healthy")

No existing column is modified or dropped.

Revision ID: b4a66af65de9
Revises: d596065649c2
Create Date: 2026-07-03 17:33:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4a66af65de9"
down_revision: str | None = "d596065649c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)

_ALERT_TYPE = postgresql.ENUM(
    "budget_threshold",
    "budget_exceeded",
    "daily_spend_spike",
    "hourly_spend_spike",
    "provider_error",
    "provider_recovery",
    "sdk_offline",
    "sdk_reconnected",
    "api_key_created",
    "api_key_revoked",
    "api_key_expired",
    "org_member_added",
    "org_member_removed",
    "high_latency",
    "rate_limit_spike",
    "large_cost_increase",
    "usage_ingestion_failure",
    "webhook_delivery_failure",
    name="alert_type",
)
_ALERT_SEVERITY = postgresql.ENUM(
    "info", "low", "medium", "high", "critical", name="alert_severity"
)
_ALERT_SEVERITY_PREF = postgresql.ENUM(
    "info", "low", "medium", "high", "critical", name="alert_severity_pref"
)
_ALERT_STATUS = postgresql.ENUM(
    "open", "acknowledged", "resolved", "dismissed", name="alert_status"
)
_ALERT_OPERATOR = postgresql.ENUM("gt", "lt", "eq", "gte", "lte", name="alert_operator")
_SUPPRESSION_SCOPE = postgresql.ENUM(
    "organization", "provider", "alert_type", name="suppression_scope"
)
_PROVIDER_HEALTH_STATUS = postgresql.ENUM(
    "unknown", "healthy", "warning", "critical", "recovering", name="provider_health_status"
)


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", _UUID, primary_key=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", _UUID, nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (
        _ALERT_TYPE,
        _ALERT_SEVERITY,
        _ALERT_SEVERITY_PREF,
        _ALERT_STATUS,
        _ALERT_OPERATOR,
        _SUPPRESSION_SCOPE,
        _PROVIDER_HEALTH_STATUS,
    ):
        enum_type.create(bind, checkfirst=True)

    # ── alert_rules ──────────────────────────────────────────────────────────
    op.create_table(
        "alert_rules",
        *_base_columns(),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("alert_type", _ALERT_TYPE, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("severity", _ALERT_SEVERITY, nullable=False, server_default="medium"),
        sa.Column("operator", _ALERT_OPERATOR, nullable=False),
        sa.Column("threshold", sa.Numeric(20, 6), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", _UUID, nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_alert_rules_organization_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_alert_rules_created_by", ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_alert_rules_cursor", "alert_rules",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_alert_rules_deleted", "alert_rules", ["deleted_at"])
    op.create_index("ix_alert_rules_org_id", "alert_rules", ["organization_id"])
    op.create_index("ix_alert_rules_org_type", "alert_rules", ["organization_id", "alert_type"])
    op.create_index("ix_alert_rules_org_enabled", "alert_rules", ["organization_id", "enabled"])

    # ── alerts ───────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        *_base_columns(),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("rule_id", _UUID, nullable=True),
        sa.Column("alert_type", _ALERT_TYPE, nullable=False),
        sa.Column("severity", _ALERT_SEVERITY, nullable=False),
        sa.Column("status", _ALERT_STATUS, nullable=False, server_default="open"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("dedup_key", sa.String(255), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("first_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_by", _UUID, nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_alerts_organization_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"], ["alert_rules.id"], name="fk_alerts_rule_id", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"], ["users.id"],
            name="fk_alerts_acknowledged_by", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_alerts_cursor", "alerts", [sa.text("created_at DESC"), sa.text("id DESC")])
    op.create_index("ix_alerts_deleted", "alerts", ["deleted_at"])
    op.create_index("ix_alerts_org_id", "alerts", ["organization_id"])
    op.create_index("ix_alerts_org_status", "alerts", ["organization_id", "status"])
    op.create_index("ix_alerts_org_type", "alerts", ["organization_id", "alert_type"])
    op.create_index("ix_alerts_org_severity", "alerts", ["organization_id", "severity"])
    op.create_index("ix_alerts_dedup_key", "alerts", ["organization_id", "dedup_key"])

    # ── alert_preferences ────────────────────────────────────────────────────
    op.create_table(
        "alert_preferences",
        *_base_columns(),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column(
            "enabled_alert_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("min_severity", _ALERT_SEVERITY_PREF, nullable=False, server_default="info"),
        sa.Column("quiet_hours_start_minute", sa.Integer(), nullable=True),
        sa.Column("quiet_hours_end_minute", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("daily_digest", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "immediate_notifications", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("max_notifications", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_alert_preferences_organization_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_alert_preferences_user_id", ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_alert_preferences_cursor", "alert_preferences",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_alert_preferences_deleted", "alert_preferences", ["deleted_at"])
    op.create_index(
        "uq_alert_preferences_org_user", "alert_preferences",
        ["organization_id", "user_id"], unique=True,
    )

    # ── alert_suppressions ───────────────────────────────────────────────────
    op.create_table(
        "alert_suppressions",
        *_base_columns(),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("scope", _SUPPRESSION_SCOPE, nullable=False),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", _UUID, nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_alert_suppressions_organization_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            name="fk_alert_suppressions_created_by", ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_alert_suppressions_cursor", "alert_suppressions",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_alert_suppressions_deleted", "alert_suppressions", ["deleted_at"])
    op.create_index("ix_alert_suppressions_org_id", "alert_suppressions", ["organization_id"])
    op.create_index(
        "ix_alert_suppressions_org_scope", "alert_suppressions",
        ["organization_id", "scope"],
    )

    # ── projects.budget ──────────────────────────────────────────────────────
    op.add_column("projects", sa.Column("budget", sa.Numeric(20, 8), nullable=True))

    # ── provider_connections health tracking ────────────────────────────────
    op.add_column(
        "provider_connections",
        sa.Column(
            "health_status", _PROVIDER_HEALTH_STATUS, nullable=False, server_default="unknown"
        ),
    )
    op.add_column(
        "provider_connections",
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column("last_recovery_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column(
            "consecutive_failure_count", sa.Integer(),
            nullable=False, server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_connections", "consecutive_failure_count")
    op.drop_column("provider_connections", "last_recovery_at")
    op.drop_column("provider_connections", "last_failure_at")
    op.drop_column("provider_connections", "health_status")
    op.drop_column("projects", "budget")

    op.drop_table("alert_suppressions")
    op.drop_table("alert_preferences")
    op.drop_table("alerts")
    op.drop_table("alert_rules")

    bind = op.get_bind()
    for enum_type in (
        _PROVIDER_HEALTH_STATUS,
        _SUPPRESSION_SCOPE,
        _ALERT_OPERATOR,
        _ALERT_STATUS,
        _ALERT_SEVERITY_PREF,
        _ALERT_SEVERITY,
        _ALERT_TYPE,
    ):
        enum_type.drop(bind, checkfirst=True)
