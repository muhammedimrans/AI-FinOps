"""SchemaSnapshot x SchemaSnapshot -> SchemaDiff — EP-14.1.

Pure function, no I/O. Every field on the returned SchemaDiff is derived
directly from the two input snapshots — nothing here infers, assumes, or
fills a gap with a guess. If a table exists on both sides, its columns/
indexes/constraints are compared by name; column *type* differences are
informational only (see models.py's docstring for why).
"""

from __future__ import annotations

from app.dbtools.models import EnumDiff, SchemaDiff, SchemaSnapshot, TableDiff


def diff_schemas(*, live: SchemaSnapshot, expected: SchemaSnapshot, revision: str) -> SchemaDiff:
    live_tables = set(live.tables)
    expected_tables = set(expected.tables)

    missing_tables = tuple(sorted(expected_tables - live_tables))
    extra_tables = tuple(sorted(live_tables - expected_tables))

    table_diffs = []
    for name in sorted(live_tables & expected_tables):
        live_t = live.tables[name]
        exp_t = expected.tables[name]

        live_cols = set(live_t.columns)
        exp_cols = set(exp_t.columns)

        table_diff = TableDiff(
            table=name,
            missing_columns=tuple(sorted(exp_cols - live_cols)),
            extra_columns=tuple(sorted(live_cols - exp_cols)),
            missing_indexes=tuple(sorted(exp_t.indexes - live_t.indexes)),
            extra_indexes=tuple(sorted(live_t.indexes - exp_t.indexes)),
            missing_constraints=tuple(sorted(exp_t.constraints - live_t.constraints)),
            extra_constraints=tuple(sorted(live_t.constraints - exp_t.constraints)),
        )
        if not table_diff.is_clean:
            table_diffs.append(table_diff)

    live_enums = set(live.enums)
    expected_enums = set(expected.enums)

    missing_enums = tuple(sorted(expected_enums - live_enums))
    extra_enums = tuple(sorted(live_enums - expected_enums))

    enum_diffs = []
    for name in sorted(live_enums & expected_enums):
        live_values = set(live.enums[name].values)
        exp_values = set(expected.enums[name].values)
        enum_diff = EnumDiff(
            name=name,
            missing_values=tuple(v for v in expected.enums[name].values if v not in live_values),
            extra_values=tuple(v for v in live.enums[name].values if v not in exp_values),
        )
        if not enum_diff.is_clean:
            enum_diffs.append(enum_diff)

    return SchemaDiff(
        revision=revision,
        missing_tables=missing_tables,
        extra_tables=extra_tables,
        missing_enums=missing_enums,
        extra_enums=extra_enums,
        table_diffs=tuple(table_diffs),
        enum_diffs=tuple(enum_diffs),
    )
