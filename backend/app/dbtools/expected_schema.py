"""Builds the SchemaSnapshot Alembic itself says a given revision produces.

Uses Alembic's offline SQL-generation mode (`command.upgrade(..., sql=True)`,
the same mechanism behind `alembic upgrade <rev> --sql`) — this never opens
a database connection. The generated DDL text is fed to `ddl_parser.py`.

Every function here is pure with respect to any live database: given the
same migrations/ directory, `expected_schema_for(revision)` always returns
the same result, computed entirely from the migration files on disk.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.script.base import Script

from app.dbtools.ddl_parser import parse_ddl
from app.dbtools.models import SchemaSnapshot


class UnparseableMigrationError(RuntimeError):
    """Raised when a migration emits DDL this project's parser doesn't
    recognize. Deliberately fatal — a silently-incomplete expected
    schema is worse than no comparison at all (see the module docstring
    in ddl_parser.py's `parse_ddl()`)."""


@dataclass(frozen=True)
class RevisionInfo:
    revision: str
    down_revision: str | None
    doc: str


def _default_ini_path() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations" / "alembic.ini"


def load_alembic_config(ini_path: Path | None = None) -> Config:
    path = ini_path or _default_ini_path()
    if not path.exists():
        raise FileNotFoundError(
            f"alembic.ini not found at {path}. Pass ini_path explicitly if "
            "migrations/alembic.ini has moved."
        )
    return Config(str(path))


def ordered_revisions(config: Config | None = None) -> list[RevisionInfo]:
    """Every revision from base to head, oldest first."""
    cfg = config or load_alembic_config()
    script = ScriptDirectory.from_config(cfg)
    revisions: list[Script] = list(script.walk_revisions(base="base", head="head"))
    revisions.reverse()  # walk_revisions() yields head-first
    result = []
    for r in revisions:
        down = r.down_revision
        down_revision = down if isinstance(down, str) or down is None else None
        result.append(
            RevisionInfo(revision=r.revision, down_revision=down_revision, doc=r.doc or "")
        )
    return result


def _generate_offline_sql(config: Config, target_revision: str) -> str:
    """Equivalent to `alembic upgrade base:<target_revision> --sql`,
    called through the Python API so no subprocess or database
    connection is involved."""
    from alembic import command

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        command.upgrade(config, f"base:{target_revision}", sql=True)
    return buffer.getvalue()


def expected_schema_for(revision: str, config: Config | None = None) -> SchemaSnapshot:
    """The SchemaSnapshot Alembic says exists once every migration from
    base through `revision` (inclusive) has run, on a schema that started
    empty. Raises UnparseableMigrationError if any statement in that
    range isn't in this parser's supported DDL vocabulary — this
    function never returns a snapshot it isn't fully confident in.
    """
    cfg = config or load_alembic_config()
    sql = _generate_offline_sql(cfg, revision)
    snapshot, unrecognized = parse_ddl(sql)
    if unrecognized:
        raise UnparseableMigrationError(
            f"{len(unrecognized)} statement(s) while building the expected "
            f"schema for revision {revision!r} were not recognized by "
            f"ddl_parser.py and must be reviewed manually before this "
            f"revision can be used as a comparison target:\n"
            + "\n".join(f"  - {s}" for s in unrecognized)
        )
    return snapshot


def head_revision(config: Config | None = None) -> str:
    cfg = config or load_alembic_config()
    script = ScriptDirectory.from_config(cfg)
    head = script.get_current_head()
    if head is None:
        raise RuntimeError("No head revision found — migrations/versions/ appears to be empty.")
    return head
