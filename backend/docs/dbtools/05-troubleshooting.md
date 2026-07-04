# Troubleshooting — EP-14.1

## "UnparseableMigrationError: N statement(s) ... were not recognized"

A migration emitted DDL outside `ddl_parser.py`'s supported vocabulary
(see its module docstring for the full list: `CREATE TABLE`,
`CREATE`/`DROP INDEX`, `CREATE TYPE ... AS ENUM`, `ALTER TYPE ... ADD
VALUE`, `ALTER TABLE ... ADD`/`DROP COLUMN`, `ADD CONSTRAINT`, `ALTER
COLUMN ... SET NOT NULL`, `DROP TABLE`/`DROP TYPE`). This is
**deliberately fatal** rather than silently skipped — a silently
incomplete expected-schema snapshot would be worse than no comparison at
all, and would violate this tool's "never guess" design goal.

Fix: extend `ddl_parser.py` with a new regex + handling branch for the
new statement shape, add a synthetic-SQL unit test for it in
`tests/test_ep14_1.py::TestDdlParserSyntheticStatements` (following the
existing pattern — one test per DDL shape), then re-run
`test_full_chain_to_head_parses_with_no_unrecognized_statements` to
confirm the whole chain parses cleanly again.

## "The report says my revision is 'far' from every candidate"

This means the live schema doesn't cleanly match any single point in
history — likely genuine, unrelated-to-Alembic drift (a manually-run
`ALTER TABLE`, a hotfix applied directly in a database console, etc.).
Open the closest candidate's diff in the report and treat each listed
item as a real, independent fact to investigate — do not assume the
whole revision needs replaying; often only 1-2 objects are actually out
of place.

## "The recommendation changed after I re-ran the tool"

Nothing in this tool caches results between runs — every invocation
re-introspects the live database and re-generates the expected schema
from whatever is currently in `migrations/versions/`. If the
recommendation changed, either (a) the live database genuinely changed
between runs (someone else applied a migration or ran manual DDL), or
(b) a new migration file was added to the repo since the last run. Check
`git log migrations/versions/` and the target database's own audit log
(if enabled) to determine which.

## "I ran this against a database with no tables at all"

Expected behavior: revision `09c89dba8c85` (the deliberate no-op
placeholder migration — see its own file, `upgrade()`/`downgrade()` are
both `pass`) will show as an exact match, since it's the only revision
that expects zero objects. The recommended stamp command in that case is
`alembic stamp 09c89dba8c85`, followed by a normal
`alembic upgrade head` to build the schema from scratch through Alembic
properly — this is the correct path for a genuinely fresh database,
distinct from the recovery scenario this EP was built for (a database
that already has objects from `create_all()`).

## "Can I run this in CI to catch drift automatically?"

Yes — `build_recommendation()` returns a plain Python object; a CI job
can call it against a staging database and fail the build if
`recommendation.exact_match is None`. This isn't wired into CI as part
of this EP (not requested), but nothing about the design prevents it —
see `02-tool-usage.md`'s "Using it programmatically" section for the
exact call shape.

## "The read-only enforcement test failed after I edited live_schema.py"

Good — that's the test doing its job. Any new query constant added to
`live_schema.py` must be named `_..._QUERY` to be picked up by
`test_no_write_verbs_in_any_live_schema_query_constant`, and must not
contain `INSERT`/`UPDATE`/`DELETE`/`CREATE`/`ALTER TABLE`/`DROP`. If your
change genuinely needs one of those verbs, it almost certainly doesn't
belong in `live_schema.py` — reconsider whether this tool should be
doing that at all (per its explicit charter: read-only, always).
