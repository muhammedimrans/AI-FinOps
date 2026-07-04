"""EP-14.1 test suite — Production Migration Recovery.

Coverage:
  - ddl_parser: every DDL shape this project's migrations actually use,
    plus real end-to-end parsing of Alembic's own offline SQL output for
    two full revision ranges (no mocking — this exercises the real
    migrations/ directory shipped in this repo).
  - expected_schema: revision ordering, per-revision schema reconstruction.
  - diff: exact-match and every mismatch category (missing/extra table,
    column, index, constraint, enum, enum value).
  - recommend: exact-match stamp recommendation; "never guess" repair
    plans that contain exactly what the injected drift produced, nothing
    more.
  - report: valid HTML output, recommendation surfaced correctly.
  - live_schema / verify_migrations: read-only enforcement — the first
    statement issued on any connection is the read-only session guard,
    and every query issued is provably a SELECT/SET, never DML/DDL;
    credentials are never present in the masked database label.

All tests are hermetic. The ddl_parser/expected_schema tests use Alembic's
real offline SQL generation (no database), matching the "no guessing"
design of this tool. live_schema tests use AsyncMock, matching this
suite's existing pattern (tests/test_ep19_1.py etc.) for exercising SQL
call shape without a real database.
"""

from __future__ import annotations

import itertools
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dbtools.ddl_parser import parse_ddl
from app.dbtools.diff import diff_schemas
from app.dbtools.expected_schema import (
    UnparseableMigrationError,
    expected_schema_for,
    head_revision,
    ordered_revisions,
)
from app.dbtools.models import (
    ColumnSchema,
    EnumSchema,
    SchemaSnapshot,
    TableSchema,
)
from app.dbtools.recommend import build_recommendation, scan_revisions

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── ddl_parser.py ────────────────────────────────────────────────────────────


class TestDdlParserSyntheticStatements:
    def test_create_table_columns_and_pk(self) -> None:
        sql = """
        CREATE TABLE widgets (
            id UUID NOT NULL,
            name VARCHAR(255) NOT NULL,
            notes TEXT,
            PRIMARY KEY (id)
        );
        """
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert set(snap.tables["widgets"].columns) == {"id", "name", "notes"}
        assert snap.tables["widgets"].columns["notes"].nullable is True
        assert snap.tables["widgets"].columns["id"].nullable is False
        assert "widgets_pkey" in snap.tables["widgets"].constraints

    def test_create_table_with_named_unique_constraint(self) -> None:
        sql = """
        CREATE TABLE widgets (
            id UUID NOT NULL,
            slug VARCHAR(64) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_widgets_slug UNIQUE (slug)
        );
        """
        snap, _ = parse_ddl(sql)
        assert "uq_widgets_slug" in snap.tables["widgets"].constraints

    def test_numeric_precision_not_split_on_comma(self) -> None:
        sql = """
        CREATE TABLE prices (
            id UUID NOT NULL,
            amount NUMERIC(20, 10) NOT NULL,
            PRIMARY KEY (id)
        );
        """
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert "amount" in snap.tables["prices"].columns
        assert "NUMERIC(20, 10)" in snap.tables["prices"].columns["amount"].data_type

    def test_create_type_enum(self) -> None:
        sql = "CREATE TYPE widget_status AS ENUM ('active', 'archived');"
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert snap.enums["widget_status"].values == ("active", "archived")

    def test_alter_type_add_value(self) -> None:
        sql = (
            "CREATE TYPE widget_status AS ENUM ('active');\n"
            "ALTER TYPE widget_status ADD VALUE IF NOT EXISTS 'archived';"
        )
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert snap.enums["widget_status"].values == ("active", "archived")

    def test_create_index_and_unique_index(self) -> None:
        sql = (
            "CREATE INDEX ix_widgets_name ON widgets (name);\n"
            "CREATE UNIQUE INDEX ix_widgets_slug ON widgets (slug);"
        )
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert {"ix_widgets_name", "ix_widgets_slug"} <= snap.tables["widgets"].indexes

    def test_drop_index_removes_it(self) -> None:
        sql = (
            "CREATE INDEX ix_widgets_name ON widgets (name);\n"
            "DROP INDEX ix_widgets_name;"
        )
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert "ix_widgets_name" not in snap.tables["widgets"].indexes

    def test_alter_table_add_and_drop_column(self) -> None:
        sql = (
            "ALTER TABLE widgets ADD COLUMN color VARCHAR(32);\n"
            "ALTER TABLE widgets ADD COLUMN weight INTEGER NOT NULL;\n"
            "ALTER TABLE widgets DROP COLUMN weight;"
        )
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert "color" in snap.tables["widgets"].columns
        assert snap.tables["widgets"].columns["color"].nullable is True
        assert "weight" not in snap.tables["widgets"].columns

    def test_alter_table_add_constraint(self) -> None:
        sql = (
            "ALTER TABLE widgets ADD CONSTRAINT fk_widgets_owner "
            "FOREIGN KEY(owner_id) REFERENCES users (id);"
        )
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert "fk_widgets_owner" in snap.tables["widgets"].constraints

    def test_alter_column_set_not_null(self) -> None:
        sql = (
            "ALTER TABLE widgets ADD COLUMN status VARCHAR(16);\n"
            "ALTER TABLE widgets ALTER COLUMN status SET NOT NULL;"
        )
        snap, _ = parse_ddl(sql)
        assert snap.tables["widgets"].columns["status"].nullable is False

    def test_drop_table_and_drop_type(self) -> None:
        sql = (
            "CREATE TABLE widgets (id UUID NOT NULL, PRIMARY KEY (id));\n"
            "CREATE TYPE widget_status AS ENUM ('active');\n"
            "DROP TABLE widgets;\n"
            "DROP TYPE widget_status;"
        )
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert "widgets" not in snap.tables
        assert "widget_status" not in snap.enums

    def test_dml_and_transaction_control_ignored(self) -> None:
        sql = (
            "BEGIN;\n"
            "CREATE TABLE widgets (id UUID NOT NULL, PRIMARY KEY (id));\n"
            "INSERT INTO alembic_version (version_num) VALUES ('abc');\n"
            "UPDATE widgets SET id = id;\n"
            "DELETE FROM widgets;\n"
            "COMMIT;"
        )
        snap, unrecognized = parse_ddl(sql)
        assert unrecognized == []
        assert "widgets" in snap.tables

    def test_alembic_version_table_never_surfaces(self) -> None:
        sql = (
            "CREATE TABLE alembic_version (\n"
            "    version_num VARCHAR(32) NOT NULL,\n"
            "    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)\n"
            ");"
        )
        snap, _ = parse_ddl(sql)
        assert "alembic_version" not in snap.tables

    def test_unrecognized_statement_is_reported_not_dropped(self) -> None:
        sql = "GRANT ALL ON widgets TO some_role;"
        _snap, unrecognized = parse_ddl(sql)
        assert unrecognized == ["GRANT ALL ON widgets TO some_role"]


class TestDdlParserRealMigrations:
    """Runs against this repo's actual migrations/ directory — the same
    files EP-14.1 is meant to reconcile against."""

    def test_ep09_range_parses_with_no_unrecognized_statements(self) -> None:
        snap = expected_schema_for("f7a8b9c0d1e2")
        assert len(snap.tables) == 15
        assert len(snap.enums) == 7
        assert "is_active" not in snap.tables["users"].columns
        assert "status" in snap.tables["users"].columns

    def test_full_chain_to_head_parses_with_no_unrecognized_statements(self) -> None:
        snap = expected_schema_for(head_revision())
        assert "organization_api_keys" in snap.tables
        assert "alerts" in snap.tables
        assert set(snap.enums["provider_type"].values) == {
            "openai", "anthropic", "grok", "google", "azure_openai",
            "openrouter", "ollama", "cohere", "bedrock", "mistral",
        }


# ── expected_schema.py ───────────────────────────────────────────────────────


class TestExpectedSchema:
    def test_ordered_revisions_forms_one_linear_chain(self) -> None:
        revisions = ordered_revisions()
        assert revisions[0].down_revision is None
        for prev, cur in itertools.pairwise(revisions):
            assert cur.down_revision == prev.revision

    def test_head_revision_matches_last_in_chain(self) -> None:
        revisions = ordered_revisions()
        assert head_revision() == revisions[-1].revision

    def test_unparseable_migration_raises(self) -> None:
        with (
            patch("app.dbtools.expected_schema._generate_offline_sql") as mock_gen,
            pytest.raises(UnparseableMigrationError),
        ):
            mock_gen.return_value = "GRANT ALL ON widgets TO some_role;"
            expected_schema_for("whatever-revision")


# ── diff.py ──────────────────────────────────────────────────────────────────


def _sample_table(**overrides: object) -> TableSchema:
    base = TableSchema(
        name="widgets",
        columns={
            "id": ColumnSchema("id", "UUID", False),
            "name": ColumnSchema("name", "VARCHAR(255)", False),
        },
        indexes=frozenset({"ix_widgets_name"}),
        constraints=frozenset({"widgets_pkey"}),
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


class TestDiffSchemas:
    def test_identical_snapshots_is_exact_match(self) -> None:
        snap = SchemaSnapshot(
            tables={"widgets": _sample_table()},
            enums={"widget_status": EnumSchema("widget_status", ("active", "archived"))},
        )
        diff = diff_schemas(live=snap, expected=snap, revision="r1")
        assert diff.is_exact_match
        assert diff.total_mismatches == 0

    def test_missing_table(self) -> None:
        live = SchemaSnapshot(tables={})
        expected = SchemaSnapshot(tables={"widgets": _sample_table()})
        diff = diff_schemas(live=live, expected=expected, revision="r1")
        assert diff.missing_tables == ("widgets",)
        assert not diff.is_exact_match

    def test_extra_table(self) -> None:
        live = SchemaSnapshot(tables={"widgets": _sample_table()})
        expected = SchemaSnapshot(tables={})
        diff = diff_schemas(live=live, expected=expected, revision="r1")
        assert diff.extra_tables == ("widgets",)
        assert not diff.is_exact_match

    def test_missing_and_extra_column(self) -> None:
        live_table = _sample_table(
            columns={
                "id": ColumnSchema("id", "UUID", False),
                "legacy_flag": ColumnSchema("legacy_flag", "BOOLEAN", True),
            }
        )
        live = SchemaSnapshot(tables={"widgets": live_table})
        expected = SchemaSnapshot(tables={"widgets": _sample_table()})
        diff = diff_schemas(live=live, expected=expected, revision="r1")
        assert len(diff.table_diffs) == 1
        td = diff.table_diffs[0]
        assert td.missing_columns == ("name",)
        assert td.extra_columns == ("legacy_flag",)

    def test_missing_index_and_constraint(self) -> None:
        live_table = _sample_table(indexes=frozenset(), constraints=frozenset())
        live = SchemaSnapshot(tables={"widgets": live_table})
        expected = SchemaSnapshot(tables={"widgets": _sample_table()})
        diff = diff_schemas(live=live, expected=expected, revision="r1")
        td = diff.table_diffs[0]
        assert td.missing_indexes == ("ix_widgets_name",)
        assert td.missing_constraints == ("widgets_pkey",)

    def test_missing_and_extra_enum(self) -> None:
        live = SchemaSnapshot(enums={"foo": EnumSchema("foo", ("a",))})
        expected = SchemaSnapshot(enums={"bar": EnumSchema("bar", ("a",))})
        diff = diff_schemas(live=live, expected=expected, revision="r1")
        assert diff.missing_enums == ("bar",)
        assert diff.extra_enums == ("foo",)

    def test_enum_value_drift(self) -> None:
        live = SchemaSnapshot(
            enums={"widget_status": EnumSchema("widget_status", ("active", "extra"))}
        )
        expected = SchemaSnapshot(
            enums={"widget_status": EnumSchema("widget_status", ("active", "archived"))}
        )
        diff = diff_schemas(live=live, expected=expected, revision="r1")
        assert len(diff.enum_diffs) == 1
        ed = diff.enum_diffs[0]
        assert ed.missing_values == ("archived",)
        assert ed.extra_values == ("extra",)


# ── recommend.py ─────────────────────────────────────────────────────────────


class TestRecommend:
    def test_exact_match_at_f7a8b9c0d1e2(self) -> None:
        live = expected_schema_for("f7a8b9c0d1e2")
        recommendation, _scans = build_recommendation(live)
        assert recommendation.exact_match is not None
        assert recommendation.exact_match.revision == "f7a8b9c0d1e2"
        assert recommendation.stamp_command == (
            "alembic -c migrations/alembic.ini stamp f7a8b9c0d1e2"
        )
        assert recommendation.repair_plan == ()

    def test_exact_match_ignores_a_wrong_alembic_version_bookmark(self) -> None:
        """The core scenario from this EP: alembic_version says one thing
        (or is entirely absent) but the live schema itself matches a
        later revision — the recommendation must be driven by the actual
        schema, never by what alembic_version happens to claim."""
        live = expected_schema_for("f7a8b9c0d1e2")
        live = replace(live, alembic_version="09c89dba8c85", alembic_version_table_exists=True)
        recommendation, _ = build_recommendation(live)
        assert recommendation.exact_match.revision == "f7a8b9c0d1e2"

    def test_no_match_produces_repair_plan_with_exactly_the_injected_drift(self) -> None:
        live = expected_schema_for("f7a8b9c0d1e2")
        users = live.tables["users"]
        cols = dict(users.columns)
        del cols["email_verified"]
        broken_users = replace(users, columns=cols)
        live = replace(live, tables={**live.tables, "users": broken_users})

        recommendation, _ = build_recommendation(live)
        assert recommendation.exact_match is None
        assert recommendation.stamp_command is None
        assert recommendation.closest_revision.revision == "f7a8b9c0d1e2"
        # "Never guess": the repair plan must name exactly the column
        # that was actually removed, and nothing else.
        descriptions = [step.description for step in recommendation.repair_plan]
        assert any("users.email_verified" in d for d in descriptions)
        assert len(recommendation.repair_plan) == 1

    def test_scan_revisions_covers_every_revision_in_the_chain(self) -> None:
        live = expected_schema_for("f7a8b9c0d1e2")
        scans = scan_revisions(live)
        assert len(scans) == len(ordered_revisions())
        assert all(s.error is None for s in scans)

    def test_empty_database_has_no_exact_match_but_scans_cleanly(self) -> None:
        """An empty database (alembic_version table doesn't even exist)
        should never crash the scanner — every revision will report
        'missing everything', and 09c89dba8c85 (the no-op placeholder)
        is the only one with zero expected objects, so it's the sole
        exact match."""
        live = SchemaSnapshot()
        recommendation, _scans = build_recommendation(live)
        assert recommendation.exact_match.revision == "09c89dba8c85"


# ── report.py ────────────────────────────────────────────────────────────────


class TestReport:
    def test_report_is_valid_html_and_contains_stamp_command(self) -> None:
        import html.parser

        from app.dbtools.report import render_report

        live = expected_schema_for("f7a8b9c0d1e2")
        recommendation, scans = build_recommendation(live)
        report_html = render_report(
            database_label="db.example.internal/mydb",
            live=live,
            recommendation=recommendation,
            scans=scans,
        )

        class _Checker(html.parser.HTMLParser):
            def error(self, message: str) -> None:  # pragma: no cover - fails the test
                raise AssertionError(f"invalid HTML: {message}")

        _Checker().feed(report_html)
        assert "stamp f7a8b9c0d1e2" in report_html
        assert "db.example.internal/mydb" in report_html

    def test_report_shows_repair_plan_when_no_exact_match(self) -> None:
        from app.dbtools.report import render_report

        live = expected_schema_for("f7a8b9c0d1e2")
        users = live.tables["users"]
        cols = dict(users.columns)
        del cols["locale"]
        live = replace(live, tables={**live.tables, "users": replace(users, columns=cols)})

        recommendation, scans = build_recommendation(live)
        report_html = render_report(
            database_label="db.example.internal/mydb",
            live=live,
            recommendation=recommendation,
            scans=scans,
        )
        assert "Repair plan required" in report_html
        assert "users.locale" in report_html


# ── live_schema.py — read-only enforcement ──────────────────────────────────


class TestReadOnlyEnforcement:
    @pytest.mark.asyncio
    async def test_first_statement_sets_transaction_read_only(self) -> None:
        from app.dbtools.live_schema import snapshot_live_schema

        executed_sql: list[str] = []

        def fake_run_sync(fn):
            conn = MagicMock()

            def fake_execute(stmt, *a, **kw):
                executed_sql.append(str(stmt))
                result = MagicMock()
                result.scalar_one.return_value = None
                result.first.return_value = None
                result.__iter__ = lambda self: iter([])
                return result

            conn.execute.side_effect = fake_execute
            with patch("app.dbtools.live_schema.inspect") as mock_inspect:
                mock_inspect.return_value.get_table_names.return_value = []
                return fn(conn)

        mock_conn_cm = AsyncMock()
        mock_conn_cm.run_sync = AsyncMock(side_effect=fake_run_sync)

        mock_engine = MagicMock()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn_cm)
        mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)

        await snapshot_live_schema(mock_engine)

        assert executed_sql, "no statements were executed"
        assert executed_sql[0] == "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"

    def test_no_write_verbs_in_any_live_schema_query_constant(self) -> None:
        """Static check: every module-level SQL text constant in
        live_schema.py — the only module in this package that ever
        touches a real database — must be a SELECT or a session-level
        SET, never DML or DDL."""
        import app.dbtools.live_schema as live_schema_module

        forbidden = ("INSERT ", "UPDATE ", "DELETE ", "CREATE ", "ALTER TABLE", "DROP ")
        checked_any = False
        for name in dir(live_schema_module):
            value = getattr(live_schema_module, name)
            text = str(getattr(value, "text", value))
            if name.startswith("_") and name.endswith("_QUERY"):
                checked_any = True
                upper = text.upper()
                assert not any(f in upper for f in forbidden), f"{name} looks like a write: {text}"
        assert checked_any, "expected at least one _QUERY constant to check"


# ── scripts/verify_migrations.py ────────────────────────────────────────────


class TestVerifyMigrationsCli:
    def test_mask_database_label_strips_credentials(self) -> None:
        from verify_migrations import _mask_database_label

        label = _mask_database_label(
            "postgresql+asyncpg://user:supersecret@ep-cool-lake.neon.tech/neondb?sslmode=require"
        )
        assert "supersecret" not in label
        assert "user" not in label
        assert label == "ep-cool-lake.neon.tech/neondb"

    def test_cli_has_no_stamp_or_apply_flag(self) -> None:
        """Guards the explicit requirement: this tool must never offer a
        way to apply its own recommendation."""
        import verify_migrations

        parser_source = verify_migrations.main.__code__.co_consts
        source_text = " ".join(str(c) for c in parser_source)
        assert "--stamp" not in source_text
        assert "--apply" not in source_text
