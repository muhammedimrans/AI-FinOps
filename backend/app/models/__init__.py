"""
ORM model package.

Import order matters for Alembic autogenerate and SQLAlchemy mapper
configuration: importing a model here causes SQLAlchemy to register it in
Base.metadata, so env.py only needs to import this package to discover all
tables.

EP-02: base infrastructure (mixins, abstract BaseModel)
EP-03: core domain models (Organization, Project, Membership, ProviderConnection)
EP-04: user identity (User, UserStatus)
EP-04.1: gap closure - UserStatus enum, username, status, email_verified,
         last_login_at, timezone, locale
EP-05: authentication — Session, VerificationToken, PasswordResetToken, password_hash
EP-08: usage collection — UsageEvent, UsageCollectionRun, UsageCollectionCheckpoint,
       ProviderUsageSummary
"""

import app.db.mixins  # noqa: F401 - registers BaseModel in Base.metadata
from app.models import base  # noqa: F401 - backward-compat re-export

# EP-19.3 - Alert engine (import after Organization, User, AlertRule; FK dependency)
from app.models.alert import (  # noqa: F401
    Alert,
    AlertOperator,
    AlertPreference,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    AlertSuppression,
    AlertType,
    SuppressionScope,
)
from app.models.daily_cost_summary import DailyCostSummary  # noqa: F401
from app.models.membership import Membership, MembershipRole  # noqa: F401

# EP-09 - Cost & Analytics Engine (import after UsageEvent and ProviderConnection; FK dependency)
from app.models.model_pricing import ModelPricing  # noqa: F401

# EP-03 - Core domain models (import order: parent before children)
from app.models.organization import Organization, OrganizationStatus  # noqa: F401

# EP-14 - Organization API keys (import after Organization and User; FK dependency)
from app.models.organization_api_key import OrganizationApiKey  # noqa: F401

# EP-05 - Auth models (import after User; all have FK to users.id)
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.models.project import Project, ProjectEnvironment  # noqa: F401
from app.models.provider_connection import ProviderConnection, ProviderType  # noqa: F401
from app.models.provider_usage_summary import ProviderUsageSummary  # noqa: F401
from app.models.session import Session  # noqa: F401
from app.models.usage_collection_checkpoint import UsageCollectionCheckpoint  # noqa: F401

# EP-08 - Usage collection (import after ProviderConnection; FK dependency)
# UsageCollectionRun must come before UsageEvent and UsageCollectionCheckpoint (FK).
from app.models.usage_collection_run import (  # noqa: F401
    CollectionRunStatus,
    CollectionTrigger,
    UsageCollectionRun,
)
from app.models.usage_cost_record import UsageCostRecord  # noqa: F401
from app.models.usage_event import UsageEvent  # noqa: F401

# EP-16 - Usage ingestion (import after Organization, Project, OrganizationApiKey; FK dependency)
from app.models.usage_record import UsageRecord, UsageRecordStatus  # noqa: F401

# EP-04 / EP-04.1 - User must be imported before Membership (FK dependency)
from app.models.user import User, UserStatus  # noqa: F401
from app.models.verification_token import VerificationToken  # noqa: F401
