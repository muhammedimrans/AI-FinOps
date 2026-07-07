"""EP-20: drop duplicate persisted external_id columns

Three earlier migrations (EP-08, EP-14, EP-16) each added a persisted,
NOT NULL, uniquely-constrained ``external_id`` column to a table whose
ORM model derives from ``BaseModel``. Every ``BaseModel``-derived model
already exposes ``external_id`` as a *computed* Python property
(``app/db/mixins.py::UUIDMixin.external_id``, e.g. ``"org_" + id.hex``)
— it is never a mapped column, is 100% derivable from the primary key
``id``, and is never queried or filtered on anywhere in the codebase
(confirmed by full-repo audit — the only reads are
``getattr(instance, "external_id")`` for API-response serialization,
which resolves to the computed property regardless of whether a
column of the same name also exists on the table).

None of the six affected models (``OrganizationApiKey``,
``UsageCollectionRun``, ``UsageEvent``, ``UsageCollectionCheckpoint``,
``ProviderUsageSummary``, ``UsageRecord``) map an ``external_id``
column, so nothing in the ORM ever populates it. A NOT NULL column
with no default that the ORM never sets makes every INSERT into these
tables fail — this migration removes it rather than adding it to the
model, since persisting it would just be redundant denormalization of
the primary key with no code path that benefits from it.

For comparison: EP-09's model_pricing migration has a stray comment
("# Required: external_id (from UUIDMixin)") but correctly does NOT
add the column — this migration brings the other six tables in line
with that (correct) precedent.

Affected tables (created by revision e6f7a8b9c0d1 / EP-08, f415de1082f8
/ EP-14, and d596065649c2 / EP-16):
  - usage_collection_runs
  - usage_events
  - usage_collection_checkpoints
  - provider_usage_summaries
  - organization_api_keys
  - usage_records

Uses IF EXISTS for every drop because this migration must be safe to
run against a database where some of these tables were originally
created via ``Base.metadata.create_all()`` rather than through the
buggy migration above — create_all() only emits columns that are
actually mapped on the model, so it would never have created this
column in the first place. Dropping a column/constraint that was never
present must be a safe no-op, not an error.

Downgrade re-adds each column as nullable (its original historical
values, if any were ever written outside the ORM, cannot be
reconstructed) — this documents the limitation rather than silently
pretending to restore prior state.

Revision ID: cf91180d80ff
Revises: b4a66af65de9
Create Date: 2026-07-07 04:12:06.451502
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cf91180d80ff"
down_revision: str | None = "b4a66af65de9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AFFECTED = (
    ("usage_collection_runs", "uq_usage_collection_runs_external_id"),
    ("usage_events", "uq_usage_events_external_id"),
    ("usage_collection_checkpoints", "uq_usage_collection_checkpoints_external_id"),
    ("provider_usage_summaries", "uq_provider_usage_summaries_external_id"),
    ("organization_api_keys", "uq_organization_api_keys_external_id"),
    ("usage_records", "uq_usage_records_external_id"),
)


def upgrade() -> None:
    for table_name, constraint_name in _AFFECTED:
        op.execute(
            f'ALTER TABLE {table_name} '
            f'DROP CONSTRAINT IF EXISTS {constraint_name}'
        )
        op.execute(
            f'ALTER TABLE {table_name} '
            f'DROP COLUMN IF EXISTS external_id'
        )


def downgrade() -> None:
    # Original values (if any were ever written outside the ORM) cannot be
    # reconstructed — this restores the column shape only, as nullable,
    # not the historical data.
    for table_name, constraint_name in _AFFECTED:
        op.add_column(
            table_name,
            sa.Column("external_id", sa.String(64), nullable=True),
        )
        op.create_unique_constraint(constraint_name, table_name, ["external_id"])
