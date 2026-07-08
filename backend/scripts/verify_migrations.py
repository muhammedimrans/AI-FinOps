#!/usr/bin/env python3
"""EP-14.1 — production-safe migration recovery verification tool.

Compares the live database's actual schema against every Alembic
revision in migrations/versions/ and reports:
  - missing tables, columns, indexes, constraints, enums
  - extra objects beyond what a revision expects
  - the current alembic_version
  - whether the live schema exactly matches some revision (-> the exact
    `alembic stamp` command to run), or a data-derived repair plan if not

This script is READ-ONLY. It never issues INSERT/UPDATE/DELETE/CREATE/
ALTER/DROP, and it never stamps or migrates anything itself — it only
prints a recommendation and writes an HTML report. See
backend/docs/dbtools/04-safety.md for exactly how that's enforced.

Usage:
  cd backend
  python -m scripts.verify_migrations
  python -m scripts.verify_migrations --output /tmp/my_report.html
  python -m scripts.verify_migrations --print-diffs
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import get_settings
from app.dbtools.live_schema import snapshot_live_schema
from app.dbtools.recommend import build_recommendation
from app.dbtools.report import render_report


def _print_diffs(scans: list) -> None:  # type: ignore[type-arg]
    """Plain-text dump of every revision's SchemaDiff — one section per
    revision, every field of TableDiff/EnumDiff printed by name so a
    mismatch is never invisible because it wasn't rendered. Read-only:
    this only prints data already computed by scan_revisions()."""
    print("\n" + "=" * 70)
    print("PER-REVISION DIAGNOSTIC DUMP")
    print("=" * 70)
    for s in scans:
        print(f"\n--- {s.info.revision}  ({s.info.doc}) ---")
        if s.error is not None:
            print(f"  UNPARSEABLE: {s.error}")
            continue
        diff = s.diff
        assert diff is not None
        print(f"  total_mismatches: {diff.total_mismatches}")
        print(f"  missing_tables: {list(diff.missing_tables)}")
        print(f"  extra_tables: {list(diff.extra_tables)}")
        print(f"  missing_enums: {list(diff.missing_enums)}")
        print(f"  extra_enums: {list(diff.extra_enums)}")
        for ed in diff.enum_diffs:
            if ed.missing_values or ed.extra_values:
                print(
                    f"  enum '{ed.name}': missing_values={list(ed.missing_values)} "
                    f"extra_values={list(ed.extra_values)}"
                )
        for td in diff.table_diffs:
            if td.is_clean:
                continue
            print(f"  table '{td.table}':")
            if td.missing_columns:
                print(f"    missing_columns: {list(td.missing_columns)}")
            if td.extra_columns:
                print(f"    extra_columns: {list(td.extra_columns)}")
            if td.missing_indexes:
                print(f"    missing_indexes: {list(td.missing_indexes)}")
            if td.extra_indexes:
                print(f"    extra_indexes: {list(td.extra_indexes)}")
            if td.missing_constraints:
                print(f"    missing_constraints: {list(td.missing_constraints)}")
            if td.extra_constraints:
                print(f"    extra_constraints: {list(td.extra_constraints)}")
    print("\n" + "=" * 70)


def _mask_database_label(database_url: str) -> str:
    """Host + database name only — never the credentials. This is the
    only representation of the connection target that ever reaches the
    generated report or stdout."""
    parts = urlsplit(database_url)
    host = parts.hostname or "unknown-host"
    port = f":{parts.port}" if parts.port else ""
    db = parts.path.lstrip("/") or "unknown-db"
    masked_netloc = f"{host}{port}"
    return urlunsplit(("", masked_netloc, f"/{db}", "", ""))[2:]


async def _run(output_path: Path, *, print_diffs: bool) -> int:
    settings = get_settings()
    database_label = _mask_database_label(settings.database_url)

    print(f"Connecting read-only to {database_label} ...")
    engine = create_async_engine(settings.database_url, echo=False)
    try:
        live = await snapshot_live_schema(engine)
    finally:
        await engine.dispose()

    print(f"Found {len(live.tables)} table(s), {len(live.enums)} enum(s).")
    if live.alembic_version_table_exists:
        print(f"alembic_version: {live.alembic_version}")
    else:
        print("alembic_version: table does not exist")

    print("Scanning every revision in migrations/versions/ ...")
    recommendation, scans = build_recommendation(live)

    if print_diffs:
        _print_diffs(scans)

    html_report = render_report(
        database_label=database_label,
        live=live,
        recommendation=recommendation,
        scans=scans,
    )
    output_path.write_text(html_report)
    print(f"\nReport written to {output_path}")

    print("\n" + "=" * 70)
    if recommendation.exact_match is not None:
        print("SAFE TO STAMP")
        print(recommendation.summary)
        print()
        print(f"  {recommendation.stamp_command}")
        print("  alembic -c migrations/alembic.ini upgrade head")
    else:
        print("REPAIR PLAN REQUIRED — do not stamp")
        print(recommendation.summary)
        print()
        for step in recommendation.repair_plan:
            print(f"  - {step.description}")
    print("=" * 70)
    print(
        "\nThis tool has not modified the database and will not run any "
        "command above for you. Review the report, then act manually."
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("migration_recovery_report.html"),
        help="Path to write the HTML report (default: ./migration_recovery_report.html)",
    )
    parser.add_argument(
        "--print-diffs",
        action="store_true",
        help=(
            "Print a plain-text per-revision diagnostic dump (every "
            "missing/extra table, column, index, constraint, and enum "
            "value) to stdout in addition to the HTML report."
        ),
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.output, print_diffs=args.print_diffs))


if __name__ == "__main__":
    raise SystemExit(main())
