"""Shared data model for schema snapshots and diffs — EP-14.1.

Both the "expected" side (built from Alembic's own DDL, see
expected_schema.py) and the "live" side (built from a real database, see
live_schema.py) are normalized into these same dataclasses, so `diff.py`
never needs to know which source a snapshot came from.

Column comparison is deliberately name + nullability based, not a strict
type-string comparison — the same column can be rendered as
"VARCHAR(255)" by Alembic's offline SQL generator and as "character
varying" by `information_schema`, which is a cosmetic difference, not a
schema drift. A `data_type` field is still carried on `ColumnSchema` for
the report to display, but `SchemaDiff` never flags a type-string
mismatch as a "missing" or "extra" object — only name/nullability
differences and object presence/absence are.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    data_type: str = ""
    nullable: bool = True


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: dict[str, ColumnSchema] = field(default_factory=dict)
    indexes: frozenset[str] = frozenset()
    constraints: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EnumSchema:
    name: str
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaSnapshot:
    """A complete picture of a schema — either what Alembic says a
    revision produces, or what a live database actually contains."""

    tables: dict[str, TableSchema] = field(default_factory=dict)
    enums: dict[str, EnumSchema] = field(default_factory=dict)
    # Only meaningful for a live snapshot; None for an expected snapshot
    # (a revision's DDL doesn't say what alembic_version *should* read —
    # that bookkeeping is a live-database-only concept).
    alembic_version: str | None = None
    alembic_version_table_exists: bool = False


@dataclass(frozen=True)
class TableDiff:
    table: str
    missing_columns: tuple[str, ...] = ()
    extra_columns: tuple[str, ...] = ()
    missing_indexes: tuple[str, ...] = ()
    extra_indexes: tuple[str, ...] = ()
    missing_constraints: tuple[str, ...] = ()
    extra_constraints: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not (
            self.missing_columns
            or self.extra_columns
            or self.missing_indexes
            or self.extra_indexes
            or self.missing_constraints
            or self.extra_constraints
        )


@dataclass(frozen=True)
class EnumDiff:
    name: str
    missing_values: tuple[str, ...] = ()
    extra_values: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not (self.missing_values or self.extra_values)


@dataclass(frozen=True)
class SchemaDiff:
    """The result of comparing a live SchemaSnapshot against an expected
    one for one specific revision. `missing_tables`/`extra_tables` are
    whole tables absent from — or present beyond — what that revision
    expects; `table_diffs`/`enum_diffs` cover tables/enums that exist on
    both sides but differ internally."""

    revision: str
    missing_tables: tuple[str, ...] = ()
    extra_tables: tuple[str, ...] = ()
    missing_enums: tuple[str, ...] = ()
    extra_enums: tuple[str, ...] = ()
    table_diffs: tuple[TableDiff, ...] = ()
    enum_diffs: tuple[EnumDiff, ...] = ()

    @property
    def is_exact_match(self) -> bool:
        """True only if the live schema has precisely the objects this
        revision expects — no more, no less. This is the sole condition
        `recommend.py` uses to propose an `alembic stamp` command."""
        return not (
            self.missing_tables
            or self.extra_tables
            or self.missing_enums
            or self.extra_enums
            or any(not d.is_clean for d in self.table_diffs)
            or any(not d.is_clean for d in self.enum_diffs)
        )

    @property
    def total_mismatches(self) -> int:
        count = len(self.missing_tables) + len(self.extra_tables)
        count += len(self.missing_enums) + len(self.extra_enums)
        for d in self.table_diffs:
            count += (
                len(d.missing_columns)
                + len(d.extra_columns)
                + len(d.missing_indexes)
                + len(d.extra_indexes)
                + len(d.missing_constraints)
                + len(d.extra_constraints)
            )
        for e in self.enum_diffs:
            count += len(e.missing_values) + len(e.extra_values)
        return count
