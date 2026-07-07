"""Parses Alembic's offline `--sql` output into a SchemaSnapshot.

This is not a general-purpose SQL parser — it covers exactly the DDL
vocabulary this project's migrations use (verified against every
migration in migrations/versions/ at the time this was written):
`CREATE TABLE`, `CREATE INDEX`/`CREATE UNIQUE INDEX`, `CREATE TYPE ... AS
ENUM`, `ALTER TYPE ... ADD VALUE`, `ALTER TABLE ... ADD COLUMN`,
`ALTER TABLE ... DROP COLUMN [IF EXISTS]`, `ALTER TABLE ... ADD
CONSTRAINT`, `ALTER TABLE ... DROP CONSTRAINT [IF EXISTS]`,
`ALTER TABLE ... ALTER COLUMN ... SET NOT NULL`, `DROP INDEX`. A
statement shape outside this list is skipped (logged, never guessed at)
rather than mis-parsed — see `parse_ddl()`'s `unrecognized` return value.

Note: no statement here is ever executed. `expected_schema.py` feeds
this module Alembic's own generated SQL *text* — there is no database
connection anywhere in this file.
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.dbtools.models import ColumnSchema, EnumSchema, SchemaSnapshot, TableSchema

_CREATE_TABLE_RE = re.compile(r"^CREATE TABLE\s+(\w+)\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL)
_CREATE_TYPE_RE = re.compile(
    r"^CREATE TYPE\s+(\w+)\s+AS ENUM\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL
)
_ALTER_TYPE_ADD_VALUE_RE = re.compile(
    r"^ALTER TYPE\s+(\w+)\s+ADD VALUE\s+(?:IF NOT EXISTS\s+)?'([^']*)'",
    re.IGNORECASE,
)
_CREATE_INDEX_RE = re.compile(
    r"^CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\w+)\s+ON\s+(\w+)\s*\(", re.IGNORECASE
)
_DROP_INDEX_RE = re.compile(r"^DROP INDEX\s+(\w+)", re.IGNORECASE)
_ALTER_ADD_COLUMN_RE = re.compile(
    r"^ALTER TABLE\s+(\w+)\s+ADD COLUMN\s+(\w+)\s+(.*)$", re.IGNORECASE | re.DOTALL
)
_ALTER_DROP_COLUMN_RE = re.compile(
    r"^ALTER TABLE\s+(\w+)\s+DROP COLUMN\s+(?:IF EXISTS\s+)?(\w+)", re.IGNORECASE
)
_ALTER_ADD_CONSTRAINT_RE = re.compile(
    r"^ALTER TABLE\s+(\w+)\s+ADD CONSTRAINT\s+(\w+)\s+(.*)$", re.IGNORECASE | re.DOTALL
)
_ALTER_DROP_CONSTRAINT_RE = re.compile(
    r"^ALTER TABLE\s+(\w+)\s+DROP CONSTRAINT\s+(?:IF EXISTS\s+)?(\w+)", re.IGNORECASE
)
_ALTER_SET_NOT_NULL_RE = re.compile(
    r"^ALTER TABLE\s+(\w+)\s+ALTER COLUMN\s+(\w+)\s+SET NOT NULL", re.IGNORECASE
)
_DROP_TABLE_RE = re.compile(r"^DROP TABLE\s+(\w+)", re.IGNORECASE)
_DROP_TYPE_RE = re.compile(r"^DROP TYPE(?:\s+IF EXISTS)?\s+(\w+)", re.IGNORECASE)

_IGNORED_PREFIXES = (
    "BEGIN",
    "COMMIT",
    "INSERT INTO",
    "DELETE FROM",
    "UPDATE ",
)
"""Statements ignored outright: `BEGIN`/`COMMIT` are transaction control,
and `INSERT`/`UPDATE`/`DELETE` are DML — every migration in this project
uses DML only for `alembic_version` bookkeeping or a one-off data backfill
(EP-04.1's is_active -> status migration), neither of which changes what
tables/columns/enums/indexes/constraints exist."""


def _split_statements(sql: str) -> list[str]:
    """Split Alembic's offline SQL dump into individual statements.

    Comment lines (`-- Running upgrade ...`) are stripped first; the
    remainder is split on `;` — safe here because none of this project's
    migrations embed a literal semicolon inside a string literal or
    identifier.
    """
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    text = "\n".join(lines)
    statements = []
    for raw in text.split(";"):
        stmt = raw.strip()
        if stmt:
            statements.append(stmt)
    return statements


def _split_top_level(body: str, sep: str = ",") -> list[str]:
    """Split on `sep` at paren-depth 0 only — `NUMERIC(20, 10)` must not
    be split into two pieces."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _parse_create_table_body(table: str, body: str) -> TableSchema:
    columns: dict[str, ColumnSchema] = {}
    constraints: set[str] = set()

    for piece in _split_top_level(body):
        upper = piece.upper()
        if upper.startswith("PRIMARY KEY"):
            constraints.add(f"{table}_pkey")
        elif upper.startswith("CONSTRAINT "):
            name = piece.split(None, 2)[1]
            constraints.add(name)
        elif (
            upper.startswith("FOREIGN KEY")
            or upper.startswith("UNIQUE")
            or upper.startswith("CHECK")
        ):
            # Anonymous constraint — this project always names its
            # constraints explicitly, so this branch exists for
            # completeness/robustness rather than an expected case.
            constraints.add(f"{table}_unnamed_constraint_{len(constraints)}")
        else:
            col_name, _, rest = piece.partition(" ")
            nullable = "NOT NULL" not in upper
            columns[col_name] = ColumnSchema(
                name=col_name, data_type=rest.strip(), nullable=nullable
            )

    return TableSchema(name=table, columns=columns, constraints=frozenset(constraints))


def parse_ddl(sql: str) -> tuple[SchemaSnapshot, list[str]]:
    """Parse Alembic offline SQL text into a SchemaSnapshot.

    Returns (snapshot, unrecognized_statements) — the second element is
    never silently dropped by callers; see expected_schema.py, which
    raises if it's non-empty, so an unhandled DDL shape fails loudly
    instead of producing a silently-incomplete comparison.
    """
    tables: dict[str, TableSchema] = {}
    enums: dict[str, EnumSchema] = {}
    unrecognized: list[str] = []

    for stmt in _split_statements(sql):
        if any(stmt.upper().startswith(p) for p in _IGNORED_PREFIXES):
            continue

        if m := _CREATE_TABLE_RE.match(stmt):
            name, body = m.group(1), m.group(2)
            tables[name] = _parse_create_table_body(name, body)
            continue

        if m := _CREATE_TYPE_RE.match(stmt):
            name, body = m.group(1), m.group(2)
            values = tuple(v.strip().strip("'") for v in _split_top_level(body))
            enums[name] = EnumSchema(name=name, values=values)
            continue

        if m := _ALTER_TYPE_ADD_VALUE_RE.match(stmt):
            name, value = m.group(1), m.group(2)
            existing = enums.get(name, EnumSchema(name=name, values=()))
            if value not in existing.values:
                enums[name] = replace(existing, values=(*existing.values, value))
            continue

        if m := _CREATE_INDEX_RE.match(stmt):
            index_name, table_name = m.group(1), m.group(2)
            t = tables.setdefault(table_name, TableSchema(name=table_name))
            tables[table_name] = replace(t, indexes=t.indexes | {index_name})
            continue

        if m := _DROP_INDEX_RE.match(stmt):
            index_name = m.group(1)
            for tname, t in tables.items():
                if index_name in t.indexes:
                    tables[tname] = replace(t, indexes=t.indexes - {index_name})
            continue

        if m := _ALTER_ADD_COLUMN_RE.match(stmt):
            table_name, col_name, rest = m.group(1), m.group(2), m.group(3)
            t = tables.setdefault(table_name, TableSchema(name=table_name))
            nullable = "NOT NULL" not in rest.upper()
            new_cols = {**t.columns, col_name: ColumnSchema(col_name, rest.strip(), nullable)}
            tables[table_name] = replace(t, columns=new_cols)
            continue

        if m := _ALTER_DROP_COLUMN_RE.match(stmt):
            table_name, col_name = m.group(1), m.group(2)
            existing_t = tables.get(table_name)
            if existing_t and col_name in existing_t.columns:
                new_cols = dict(existing_t.columns)
                del new_cols[col_name]
                tables[table_name] = replace(existing_t, columns=new_cols)
            continue

        if m := _ALTER_ADD_CONSTRAINT_RE.match(stmt):
            table_name, constraint_name = m.group(1), m.group(2)
            t = tables.setdefault(table_name, TableSchema(name=table_name))
            tables[table_name] = replace(t, constraints=t.constraints | {constraint_name})
            continue

        if m := _ALTER_DROP_CONSTRAINT_RE.match(stmt):
            table_name, constraint_name = m.group(1), m.group(2)
            existing_t = tables.get(table_name)
            if existing_t and constraint_name in existing_t.constraints:
                tables[table_name] = replace(
                    existing_t, constraints=existing_t.constraints - {constraint_name}
                )
            continue

        if m := _ALTER_SET_NOT_NULL_RE.match(stmt):
            table_name, col_name = m.group(1), m.group(2)
            existing_t = tables.get(table_name)
            if existing_t and col_name in existing_t.columns:
                new_cols = dict(existing_t.columns)
                new_cols[col_name] = replace(new_cols[col_name], nullable=False)
                tables[table_name] = replace(existing_t, columns=new_cols)
            continue

        if m := _DROP_TABLE_RE.match(stmt):
            tables.pop(m.group(1), None)
            continue

        if m := _DROP_TYPE_RE.match(stmt):
            enums.pop(m.group(1), None)
            continue

        unrecognized.append(stmt)

    tables.pop("alembic_version", None)
    return SchemaSnapshot(tables=tables, enums=enums), unrecognized
