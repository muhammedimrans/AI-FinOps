"""
SQLAlchemy DeclarativeBase — single source of truth for Base.metadata.

All ORM models must inherit (transitively) from Base so that Alembic
autogenerate can detect schema changes.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all AI FinOps ORM models."""
