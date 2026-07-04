"""Read-only introspection of the actual target database — EP-14.1.

Read-only guarantee
--------------------
Every query issued by this module is a `SELECT` against either
`information_schema`, `pg_catalog`, or SQLAlchemy's `Inspector` (which is
itself backed by the same catalog `SELECT`s). Nothing here ever
constructs `INSERT`/`UPDATE`/`DELETE`/`CREATE`/`ALTER`/`DROP`.

As a second, independent layer of defense (belt *and* suspenders — code
review can miss a mistake, a database-level rejection cannot), every
connection opened by `snapshot_live_schema()` immediately issues
`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` before running any
introspection query. If a future change to this module ever tried to
write, Postgres itself would reject it with an error — the guarantee
doesn't rely solely on this file's own code staying correct.
`tests/test_dbtools.py::TestReadOnlyEnforcement` asserts this statement
is issued before any other query on every code path.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.dbtools.models import ColumnSchema, EnumSchema, SchemaSnapshot, TableSchema

_ENUMS_QUERY = text(
    "SELECT t.typname, e.enumlabel "
    "FROM pg_type t "
    "JOIN pg_enum e ON t.oid = e.enumtypid "
    "JOIN pg_namespace n ON n.oid = t.typnamespace "
    "WHERE n.nspname = 'public' "
    "ORDER BY t.typname, e.enumsortorder"
)

_ALEMBIC_VERSION_TABLE_QUERY = text("SELECT to_regclass('public.alembic_version')")

_ALEMBIC_VERSION_ROW_QUERY = text("SELECT version_num FROM alembic_version LIMIT 1")


def _inspect_tables(conn: Connection) -> dict[str, TableSchema]:
    """Runs entirely through SQLAlchemy's Inspector — every method here
    (`get_table_names`, `get_columns`, `get_indexes`, `get_pk_constraint`,
    `get_unique_constraints`, `get_foreign_keys`) issues read-only catalog
    queries under the hood; none of them accept a write path."""
    inspector = inspect(conn)
    tables: dict[str, TableSchema] = {}

    for table_name in inspector.get_table_names(schema="public"):
        if table_name == "alembic_version":
            continue

        columns = {
            col["name"]: ColumnSchema(
                name=col["name"],
                data_type=str(col["type"]),
                nullable=col.get("nullable", True),
            )
            for col in inspector.get_columns(table_name, schema="public")
        }

        index_names = {
            idx["name"]
            for idx in inspector.get_indexes(table_name, schema="public")
            if idx["name"] is not None
        }

        constraint_names: set[str] = set()
        pk = inspector.get_pk_constraint(table_name, schema="public")
        pk_name = pk.get("name")
        if pk_name:
            constraint_names.add(pk_name)
        for uc in inspector.get_unique_constraints(table_name, schema="public"):
            uc_name = uc.get("name")
            if uc_name:
                constraint_names.add(uc_name)
        for fk in inspector.get_foreign_keys(table_name, schema="public"):
            fk_name = fk.get("name")
            if fk_name:
                constraint_names.add(fk_name)

        tables[table_name] = TableSchema(
            name=table_name,
            columns=columns,
            indexes=frozenset(index_names),
            constraints=frozenset(constraint_names),
        )

    return tables


def _inspect_enums(conn: Connection) -> dict[str, EnumSchema]:
    result = conn.execute(_ENUMS_QUERY)
    enums: dict[str, list[str]] = {}
    for typname, enumlabel in result:
        enums.setdefault(typname, []).append(enumlabel)
    return {name: EnumSchema(name=name, values=tuple(values)) for name, values in enums.items()}


def _inspect_alembic_version(conn: Connection) -> tuple[bool, str | None]:
    exists = conn.execute(_ALEMBIC_VERSION_TABLE_QUERY).scalar_one() is not None
    if not exists:
        return False, None
    row = conn.execute(_ALEMBIC_VERSION_ROW_QUERY).first()
    return True, (row[0] if row else None)


def _snapshot_sync(conn: Connection) -> SchemaSnapshot:
    # Enforced read-only at the database level — see the module docstring.
    conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))

    tables = _inspect_tables(conn)
    enums = _inspect_enums(conn)
    version_table_exists, version = _inspect_alembic_version(conn)

    return SchemaSnapshot(
        tables=tables,
        enums=enums,
        alembic_version=version,
        alembic_version_table_exists=version_table_exists,
    )


async def snapshot_live_schema(engine: AsyncEngine) -> SchemaSnapshot:
    """The single entry point this package uses to read a live database.

    Opens one connection, sets it read-only at the Postgres session
    level, introspects, and always rolls back on exit (`engine.connect()`
    does not autocommit) — no write is possible on this code path even in
    principle.
    """
    async with engine.connect() as conn:
        return await conn.run_sync(_snapshot_sync)
