# Report Format — EP-14.1

The HTML report (`app/dbtools/report.py`) is a single self-contained
file — no external CSS/JS/fonts, safe to open locally or attach to an
incident ticket without a network connection.

## Sections

**Header** — target database (masked host/db name, never credentials)
and the generation timestamp, plus an explicit "read-only scan" notice.

**Recommendation** — the single most important panel. Two states:

- *Safe to stamp* (teal): the live schema exactly matches one revision.
  Shows the exact `alembic stamp` + `alembic upgrade head` commands —
  as text to copy, never as something the report or tool executes.
- *Repair plan required* (amber): no exact match. Lists every
  missing/extra object as a bullet, each derived directly from the diff
  against the closest revision — never a fabricated suggestion.

**Current state** — `alembic_version`'s literal value (or "table does
not exist"), and the raw table/enum counts found live.

**Revision-by-revision scan** — one row per migration in the chain, in
order, each with a pill:

| Pill | Meaning |
|---|---|
| `exact match` (teal) | Zero mismatches against this revision |
| `N mismatch(es)` (amber, 1-3) | Close but not exact |
| `N mismatch(es)` (red, 4+) | Far from this revision |
| `unparseable` (red) | This revision's migrations use DDL the parser doesn't recognize — see `05-troubleshooting.md` |

Clicking "show diff" on any non-exact row expands the specific missing/
extra tables, columns, indexes, constraints, and enum values for that
revision — this is what lets you see, at a glance, which historical
point the database is closest to even when it isn't an exact match.

## What "missing" vs "extra" means at a given revision

For any revision **before** where the live schema actually sits, objects
from later migrations will correctly show up as "extra" — that's not an
anomaly, it just means the live database is further along than that
particular candidate. The revision-by-revision view makes this obvious:
extras shrink and missings disappear as you scan toward the true match
point, then extras grow again past it. The single revision where **both**
are empty is the real match (see `app/dbtools/models.py`'s
`SchemaDiff.is_exact_match` and the design note in `recommend.py`'s
module docstring for why at most one such revision can exist in a chain
that never drops objects on the upgrade path).

## Column type differences are informational only

The report tracks columns by name and nullability. A cosmetic type
rendering difference (e.g. Alembic's offline SQL saying `VARCHAR(255)`
vs. `information_schema` reporting `character varying`) is not flagged
as a mismatch — see `app/dbtools/models.py`'s docstring for the
reasoning. If you need to verify exact column types, cross-reference the
migration file directly; the report's job is to catch structural drift
(missing/extra objects), not cosmetic formatting differences.
