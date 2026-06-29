"""
Database infrastructure package.

Public surface re-exported here for convenience. Internal modules:
  base.py         — SQLAlchemy DeclarativeBase
  mixins.py       — uuid7, ORM mixins, BaseModel
  engine.py       — async engine factory, health check
  session.py      — session factory, managed_transaction
  dependencies.py — FastAPI get_session dependency
  init_db.py      — startup/teardown helpers
"""
from app.db.base import Base
from app.db.dependencies import get_session
from app.db.engine import check_database, create_engine
from app.db.mixins import (
    BaseModel,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    uuid7,
)
from app.db.session import create_session_factory, managed_transaction

__all__ = [
    "Base",
    "BaseModel",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDMixin",
    "check_database",
    "create_engine",
    "create_session_factory",
    "get_session",
    "managed_transaction",
    "uuid7",
]
