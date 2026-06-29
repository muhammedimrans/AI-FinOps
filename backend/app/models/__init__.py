"""
ORM model package.

Import order matters for Alembic autogenerate: importing a model here causes
SQLAlchemy to register it in Base.metadata, so env.py only needs to import
this package to discover all tables.

Add imports here as models are implemented in future EPs:
    from app.models import organization, project, ...  # noqa: F401
"""

import app.db.mixins  # noqa: F401 — registers BaseModel in Base.metadata
from app.models import base  # noqa: F401 — backward-compat re-export
