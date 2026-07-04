# EP-14.1 — Production Migration Recovery

## Why this exists

Production's schema was originally created via `Base.metadata.create_all()`
(`app/db/init_db.py`) before Alembic was introduced (see EP-14/backend
production-incident conversations). That mechanism never writes to
`alembic_version`, so the bookkeeping table can say one thing while the
real schema says another — which is exactly what caused two production
incidents: a missing `organization_api_keys` table, then a
`DuplicateObjectError` on `organization_status` when Alembic finally ran
for the first time and tried to replay the whole migration history from
scratch.

This EP builds a tool that answers one question, safely: **which
Alembic revision (if any) does the live database's schema actually
match, and if none, exactly what's different?** — without ever running a
single write against the database, and without ever guessing an answer
the live schema doesn't itself support.

## Architecture

```
                    ┌─────────────────────┐
                    │  migrations/*.py     │  (unchanged — this EP reads
                    │  (the source of      │   them, never edits them)
                    │   truth)             │
                    └──────────┬───────────┘
                               │ alembic upgrade base:<rev> --sql
                               │ (offline — no DB connection)
                               ▼
                    ┌─────────────────────┐
                    │ expected_schema.py   │──▶ ddl_parser.py ──▶ SchemaSnapshot
                    └─────────────────────┘

                    ┌─────────────────────┐
   live database ──▶│  live_schema.py      │──▶ SchemaSnapshot
   (read-only)       │  (SET ... READ ONLY  │
                      │   + SELECT only)     │
                      └─────────────────────┘

         SchemaSnapshot (expected) × SchemaSnapshot (live)
                               │
                               ▼
                          diff.py ──▶ SchemaDiff
                               │
                               ▼
                        recommend.py
                   (scans every revision)
                       /              \
        exact match found?      no match found
              │                        │
              ▼                        ▼
     "stamp <revision>"      data-derived repair plan
              \                        /
               \                      /
                ▼                    ▼
                     report.py
              (self-contained HTML file)
```

## What it produces

- A recommendation: either the exact `alembic stamp <revision>` command
  to run, or a repair plan built entirely from the diff's own fields
  (never fabricated).
- A revision-by-revision scan table showing how close the live schema
  is to each point in history.
- An HTML report (`migration_recovery_report.html` by default) suitable
  for attaching to an incident ticket.

## What it never does

- Never opens a write transaction, never issues DDL/DML against the
  target database (`docs/dbtools/04-safety.md` has the full enforcement
  chain).
- Never stamps, migrates, or applies its own repair plan — the CLI has
  no `--stamp`/`--apply` flag by design.
- Never includes the database connection string or credentials in its
  output — only a masked `host/database` label.

## Files

| Path | Purpose |
|---|---|
| `app/dbtools/models.py` | Shared dataclasses (`SchemaSnapshot`, `TableSchema`, `SchemaDiff`, ...) |
| `app/dbtools/ddl_parser.py` | Parses Alembic's offline SQL text into a `SchemaSnapshot` |
| `app/dbtools/expected_schema.py` | Runs Alembic in offline mode per revision, no DB connection |
| `app/dbtools/live_schema.py` | Read-only introspection of the real target database |
| `app/dbtools/diff.py` | `SchemaSnapshot x SchemaSnapshot -> SchemaDiff` |
| `app/dbtools/recommend.py` | Scans every revision, builds the stamp/repair recommendation |
| `app/dbtools/report.py` | Renders the HTML report |
| `scripts/verify_migrations.py` | CLI entry point |
| `tests/test_ep14_1.py` | 37 tests covering every module above |
