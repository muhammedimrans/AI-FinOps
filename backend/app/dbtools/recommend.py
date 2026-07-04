"""Scans every revision and derives a recommendation — never a guess.

`scan_revisions()` computes a `SchemaDiff` for the live snapshot against
*every* revision in the chain, oldest to newest. Because this project's
migration chain never drops a table/enum on the upgrade path (verified:
every `downgrade()` reverses its own `upgrade()`, and no migration's
`upgrade()` removes an object a prior migration added), the cumulative
object set is strictly increasing revision-over-revision — which means
at most one revision can satisfy `SchemaDiff.is_exact_match` (zero
missing *and* zero extra). `build_recommendation()` looks for that one
revision; if none exists, it reports the closest candidate — the
revision with the fewest total mismatches — and turns that diff directly
into a repair plan. Nothing here is inferred beyond what the diff data
itself says.
"""

from __future__ import annotations

from dataclasses import dataclass

from alembic.config import Config

from app.dbtools.diff import diff_schemas
from app.dbtools.expected_schema import (
    RevisionInfo,
    UnparseableMigrationError,
    expected_schema_for,
    ordered_revisions,
)
from app.dbtools.models import SchemaDiff, SchemaSnapshot


@dataclass(frozen=True)
class RevisionScan:
    info: RevisionInfo
    diff: SchemaDiff | None
    error: str | None = None


@dataclass(frozen=True)
class RepairStep:
    """One concrete, data-derived action. `sql` is a *draft* statement for
    a human to review — this package never executes it."""

    description: str
    sql: str


@dataclass(frozen=True)
class Recommendation:
    exact_match: RevisionInfo | None
    stamp_command: str | None
    closest_revision: RevisionInfo | None
    closest_diff: SchemaDiff | None
    repair_plan: tuple[RepairStep, ...]
    summary: str


def scan_revisions(
    live: SchemaSnapshot, config: Config | None = None
) -> list[RevisionScan]:
    """Diff `live` against every revision in the chain. A revision whose
    migrations use DDL this parser doesn't recognize is reported with
    `error` set rather than silently skipped or guessed at."""
    scans: list[RevisionScan] = []
    for info in ordered_revisions(config):
        try:
            expected = expected_schema_for(info.revision, config)
        except UnparseableMigrationError as exc:
            scans.append(RevisionScan(info=info, diff=None, error=str(exc)))
            continue
        diff = diff_schemas(live=live, expected=expected, revision=info.revision)
        scans.append(RevisionScan(info=info, diff=diff))
    return scans


def _repair_plan_from_diff(diff: SchemaDiff) -> tuple[RepairStep, ...]:
    """Turns a SchemaDiff's own fields into draft repair steps — every
    step is one specific missing/extra object this exact diff reported,
    nothing synthesized beyond that."""
    steps: list[RepairStep] = []

    for table in diff.missing_tables:
        steps.append(
            RepairStep(
                description=f"Table '{table}' is missing entirely.",
                sql=(
                    f"-- '{table}' does not exist. Regenerate its CREATE TABLE\n"
                    f"-- from the migration that defines it (see the revision\n"
                    f"-- history) rather than hand-writing DDL here — copying\n"
                    f"-- verbatim guarantees indexes/constraints/defaults match."
                ),
            )
        )

    for table in diff.extra_tables:
        steps.append(
            RepairStep(
                description=(
                    f"Table '{table}' exists in the live database but is not "
                    f"expected at revision {diff.revision}. This usually means "
                    f"the live schema is further ahead than this candidate "
                    f"revision, not that '{table}' needs to be dropped — check "
                    f"which later revision defines it before taking any action."
                ),
                sql="-- informational only — do not drop without further investigation",
            )
        )

    for td in diff.table_diffs:
        for col in td.missing_columns:
            steps.append(
                RepairStep(
                    description=f"Column '{td.table}.{col}' is missing.",
                    sql=f"-- ALTER TABLE {td.table} ADD COLUMN {col} <type from migration file>;",
                )
            )
        for col in td.extra_columns:
            steps.append(
                RepairStep(
                    description=(
                        f"Column '{td.table}.{col}' exists live but isn't expected "
                        f"at revision {diff.revision} — verify before dropping."
                    ),
                    sql="-- informational only — do not drop without further investigation",
                )
            )
        for idx in td.missing_indexes:
            steps.append(
                RepairStep(
                    description=f"Index '{idx}' on '{td.table}' is missing.",
                    sql=f"-- CREATE INDEX {idx} ON {td.table} (<columns from migration file>);",
                )
            )
        for constraint in td.missing_constraints:
            steps.append(
                RepairStep(
                    description=f"Constraint '{constraint}' on '{td.table}' is missing.",
                    sql=(
                        f"-- ALTER TABLE {td.table} ADD CONSTRAINT {constraint} "
                        f"<definition from migration file>;"
                    ),
                )
            )

    for table in diff.missing_enums:
        steps.append(
            RepairStep(
                description=f"Enum type '{table}' is missing.",
                sql=f"-- CREATE TYPE {table} AS ENUM (<values from migration file>);",
            )
        )

    for ed in diff.enum_diffs:
        for value in ed.missing_values:
            steps.append(
                RepairStep(
                    description=f"Enum '{ed.name}' is missing value '{value}'.",
                    sql=f"ALTER TYPE {ed.name} ADD VALUE IF NOT EXISTS '{value}';",
                )
            )
        for value in ed.extra_values:
            steps.append(
                RepairStep(
                    description=(
                        f"Enum '{ed.name}' has value '{value}' that isn't expected "
                        f"at revision {diff.revision} — Postgres cannot drop enum "
                        f"values; this is informational only."
                    ),
                    sql="-- Postgres has no ALTER TYPE ... DROP VALUE — informational only",
                )
            )

    return tuple(steps)


def build_recommendation(
    live: SchemaSnapshot, config: Config | None = None
) -> tuple[Recommendation, list[RevisionScan]]:
    scans = scan_revisions(live, config)
    parseable = [s for s in scans if s.diff is not None]

    exact = next((s for s in parseable if s.diff.is_exact_match), None)  # type: ignore[union-attr]

    if exact is not None:
        stamp_cmd = f"alembic -c migrations/alembic.ini stamp {exact.info.revision}"
        return (
            Recommendation(
                exact_match=exact.info,
                stamp_command=stamp_cmd,
                closest_revision=None,
                closest_diff=None,
                repair_plan=(),
                summary=(
                    f"The live schema exactly matches revision {exact.info.revision} "
                    f"({exact.info.doc}). No repair is needed — stamping this "
                    f"revision and then running `alembic upgrade head` will apply "
                    f"only the migrations genuinely missing."
                ),
            ),
            scans,
        )

    if not parseable:
        return (
            Recommendation(
                exact_match=None,
                stamp_command=None,
                closest_revision=None,
                closest_diff=None,
                repair_plan=(),
                summary=(
                    "No revision could be evaluated — every migration in the chain "
                    "produced DDL this tool's parser doesn't recognize. Review the "
                    "per-revision errors in the full scan before proceeding."
                ),
            ),
            scans,
        )

    closest = min(parseable, key=lambda s: s.diff.total_mismatches)  # type: ignore[union-attr]
    repair_plan = _repair_plan_from_diff(closest.diff)  # type: ignore[arg-type]

    return (
        Recommendation(
            exact_match=None,
            stamp_command=None,
            closest_revision=closest.info,
            closest_diff=closest.diff,
            repair_plan=repair_plan,
            summary=(
                f"No revision matches exactly. The closest is "
                f"{closest.info.revision} ({closest.info.doc}) with "
                f"{closest.diff.total_mismatches} mismatch(es) — see the repair "  # type: ignore[union-attr]
                f"plan below. Do not stamp any revision until these are resolved; "
                f"a stamp on a non-matching revision hides real drift instead of "
                f"fixing it."
            ),
        ),
        scans,
    )
