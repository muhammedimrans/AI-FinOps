"""
Backward-compatibility shim — do not add new code here.

All database infrastructure has moved to app.db.*. This module preserves
existing import paths (health.py, container.py, migrations/env.py, tests)
without requiring a refactor sweep.

New code should import from app.db directly:
  from app.db import Base, create_engine, get_session, ...
"""
from __future__ import annotations

from app.db.base import Base as Base
from app.db.dependencies import get_session as get_session
from app.db.engine import check_database as check_database
from app.db.engine import create_engine as create_engine
from app.db.session import create_session_factory as create_session_factory
from app.db.session import managed_transaction as managed_transaction

__all__ = [
    "Base",
    "create_engine",
    "create_session_factory",
    "check_database",
    "get_session",
    "managed_transaction",
]
