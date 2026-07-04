# Safety — EP-14.1's Read-Only Guarantee

This tool was built specifically to be run against **production** during
an active incident, so its read-only guarantee is load-bearing, not a
nice-to-have. This document is the complete list of everything that
enforces it.

## Layer 1 — only one module ever opens a connection

Of the seven `app/dbtools/*.py` modules, exactly one —
`live_schema.py` — ever receives a live database engine.
`expected_schema.py` computes the "expected" side entirely through
Alembic's **offline SQL-generation mode**
(`alembic.command.upgrade(..., sql=True)`), which the Alembic project
itself designed to run with no database connection at all — it emits SQL
*text*, nothing more. `ddl_parser.py`, `diff.py`, `recommend.py`, and
`report.py` are pure functions over Python data structures; none of them
import a database driver.

## Layer 2 — every query in `live_schema.py` is a `SELECT`

The complete list of statements this tool can ever send to a live
database:

| Statement | Purpose |
|---|---|
| `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` | Session-level guard, see Layer 3 |
| `SELECT ... FROM information_schema.tables` (via `sqlalchemy.inspect()`) | Table names |
| `SELECT ... FROM information_schema.columns` (via `inspect()`) | Column names/types/nullability |
| `SELECT ... FROM pg_indexes` (via `inspect()`) | Index names |
| `SELECT ... FROM pg_constraint` (via `inspect()`) | PK/FK/unique constraint names |
| `SELECT t.typname, e.enumlabel FROM pg_type ... JOIN pg_enum ...` | Enum types and their values |
| `SELECT to_regclass('public.alembic_version')` | Does the bookkeeping table exist |
| `SELECT version_num FROM alembic_version LIMIT 1` | The current stamped revision |

That's the entire surface. `tests/test_ep14_1.py::TestReadOnlyEnforcement
::test_no_write_verbs_in_any_live_schema_query_constant` statically
scans every module-level `_..._QUERY` constant in `live_schema.py` for
`INSERT`/`UPDATE`/`DELETE`/`CREATE`/`ALTER TABLE`/`DROP` and fails the
suite if any appear — a future change that accidentally introduces a
write constant breaks CI, not production.

## Layer 3 — database-level enforcement, independent of this code being correct

Before any introspection query runs, `live_schema.py` issues:

```sql
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY
```

This is Postgres's own read-only transaction mode — if any future bug in
this codebase ever tried to write, **Postgres itself rejects the
statement**, not just this tool's own logic. This is deliberately
redundant with Layer 2: code review can miss a mistake; a database-level
rejection cannot be bypassed by a bug in the reviewing code.
`tests/test_ep14_1.py::TestReadOnlyEnforcement::
test_first_statement_sets_transaction_read_only` asserts this is
literally the first statement executed on every code path through
`snapshot_live_schema()`.

The connection is also never committed — `engine.connect()` (not
`engine.begin()`) is used, and the `async with` block's exit always
rolls back implicitly. There is no code path that calls `.commit()`
anywhere in this package.

## Layer 4 — the CLI has no execution flag

`scripts/verify_migrations.py`'s `argparse` setup has exactly one
option: `--output` (where to write the report). There is no `--stamp`,
`--apply`, `--fix`, `--yes`, or any flag that would cause this tool to
act on its own recommendation.
`tests/test_ep14_1.py::TestVerifyMigrationsCli::
test_cli_has_no_stamp_or_apply_flag` guards this by inspecting the
compiled bytecode constants of `main()` for those flag strings.

## Layer 5 — credentials never leave the process

`_mask_database_label()` strips everything except the host and database
name from `DATABASE_URL` before it's used anywhere — printed to stdout,
embedded in the HTML report, or logged. The username, password, and any
query-string parameters (e.g. `sslmode=require`) are discarded.
`tests/test_ep14_1.py::TestVerifyMigrationsCli::
test_mask_database_label_strips_credentials` verifies this directly
against a synthetic DSN containing a fake secret.

## What this does NOT protect against

- A network-level compromise of the machine running this script (out of
  scope for this tool — that's infrastructure security, not this code).
- A malicious/compromised Postgres server ignoring the client's
  `SET ... READ ONLY` request — not a realistic threat model for this
  project's own Neon-hosted production database, but worth stating: this
  tool trusts the target database to honor its own session-level
  read-only mode, same as every other read-only tool built on top of
  standard Postgres protocol semantics.
