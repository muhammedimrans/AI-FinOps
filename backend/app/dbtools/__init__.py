"""Migration recovery tooling — EP-14.1.

Production's schema was originally created via `Base.metadata.create_all()`
(see `app/db/init_db.py`) before Alembic was introduced, so its
`alembic_version` bookkeeping does not necessarily reflect what objects
actually exist. This package answers one question, read-only, without ever
guessing: **which Alembic revision (if any) does the live database's schema
exactly match, and if none, exactly what is missing or extra relative to
the closest one.**

Modules
-------
models.py           Plain dataclasses shared by every other module —
                     TableSchema, SchemaSnapshot, SchemaDiff.
ddl_parser.py        Parses Alembic's offline `--sql` output (plain DDL
                     text, no database involved) into a SchemaSnapshot.
expected_schema.py   Invokes Alembic in offline SQL-generation mode for a
                     given revision and returns the SchemaSnapshot Alembic
                     itself says that revision produces.
live_schema.py       Read-only SQLAlchemy introspection of the actual
                     target database into the same SchemaSnapshot shape.
diff.py              SchemaSnapshot x SchemaSnapshot -> SchemaDiff.
recommend.py         Scans every revision in the chain, finds an exact
                     match (-> stamp recommendation) or the closest one
                     (-> a repair plan built only from that diff's data).
report.py            Renders a SchemaDiff + recommendation into a
                     self-contained HTML report.

Safety
------
Every function that touches a live database issues `SELECT` statements
only (SQLAlchemy's `sqlalchemy.inspect()` and two catalog queries for
enums/alembic_version — see live_schema.py's docstring for the exact
list). Nothing in this package ever constructs `INSERT`/`UPDATE`/`DELETE`/
`CREATE`/`ALTER`/`DROP`. `verify_migrations.py` (the CLI entry point) does
not accept a `--stamp` or `--apply` flag — recommending a command is not
the same as running it, and this tool deliberately stops at the
recommendation. See docs/dbtools/04-safety.md for the enforcement details
and how the test suite verifies this claim.
"""
