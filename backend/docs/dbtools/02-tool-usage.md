# Tool Usage — EP-14.1

## Running it

```bash
cd backend
python -m scripts.verify_migrations
```

By default this reads `DATABASE_URL` from the environment (the same
`Settings` object every other backend entry point uses — see
`app/config/settings.py`) and writes `migration_recovery_report.html` in
the current directory.

To write the report somewhere else:

```bash
python -m scripts.verify_migrations --output /tmp/incident-2026-07-04.html
```

There is no `--stamp`, `--apply`, `--fix`, or `--yes` flag. This is
deliberate — see `04-safety.md`.

## Against production

Point `DATABASE_URL` at production **for the duration of this command
only** — it never writes, so this is safe to run directly against a live
database (this is in fact the intended use case: verifying production's
actual state during an incident). If you'd rather not point any tool at
production directly, restore a recent backup/snapshot into a scratch
Postgres instance and run the tool against that instead — the two will
report the same result unless production has changed since the backup
was taken.

```bash
DATABASE_URL="postgresql+asyncpg://user:pass@prod-host/dbname" \
  python -m scripts.verify_migrations --output prod_recovery_report.html
```

## Reading the output

The script prints a summary to stdout and writes the full HTML report.
Two possible outcomes:

**Exact match found:**
```
======================================================================
SAFE TO STAMP
The live schema exactly matches revision f7a8b9c0d1e2 (EP-09: Cost & Analytics Engine).
No repair is needed — stamping this revision and then running `alembic upgrade head`
will apply only the migrations genuinely missing.

  alembic -c migrations/alembic.ini stamp f7a8b9c0d1e2
  alembic -c migrations/alembic.ini upgrade head
======================================================================

This tool has not modified the database and will not run any command
above for you. Review the report, then act manually.
```

**No exact match — repair plan required:**
```
======================================================================
REPAIR PLAN REQUIRED — do not stamp
No revision matches exactly. The closest is f7a8b9c0d1e2 (EP-09: Cost & Analytics Engine)
with 1 mismatch(es) — see the repair plan below. Do not stamp any revision until these
are resolved; a stamp on a non-matching revision hides real drift instead of fixing it.

  - Column 'users.email_verified' is missing.
======================================================================
```

In both cases, open the HTML report for the full revision-by-revision
breakdown — every table, column, index, constraint, and enum this tool
checked, and exactly what (if anything) didn't match at each candidate
revision.

## Using it programmatically

Every function is importable and composable without the CLI:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from app.dbtools.live_schema import snapshot_live_schema
from app.dbtools.recommend import build_recommendation

engine = create_async_engine(database_url)
live = await snapshot_live_schema(engine)
recommendation, scans = build_recommendation(live)

if recommendation.exact_match:
    print(f"stamp {recommendation.exact_match.revision}")
else:
    for step in recommendation.repair_plan:
        print(step.description)
```

## Extending it to a new revision

Nothing to do — `ordered_revisions()` reads `migrations/versions/`
directly, so a new migration is automatically included in the next scan.
The only action needed is if a future migration uses DDL outside this
project's established vocabulary (see `docs/dbtools/05-troubleshooting.md`
for what to do when `UnparseableMigrationError` is raised).
