# EP-03 Knowledge Transfer — Core Domain Models

| Field | Value |
|---|---|
| **Epic** | EP-03 — Core Domain Models |
| **Status** | Complete |
| **Author** | Principal Backend Engineer / AI FinOps |
| **Date** | 2026-06-29 |
| **Audience** | New and existing backend engineers |
| **Prerequisites** | EP-01 (Repository Foundation), EP-02 (Database Infrastructure) |
| **Feeds** | EP-04 (Identity, RBAC, and REST APIs) |

> **Purpose.** This document is the engineering knowledge transfer for EP-03. It explains what was built, why it was built, the design decisions behind it, and the foundational concepts every engineer needs to understand before contributing to AI FinOps. Read it from start to finish before writing any code in this repository.

---

## Section 1 — Implementation Review

### What Was Implemented

EP-03 introduced the four core business entities of the AI FinOps platform. These are the first real data models — the tables that will store the organization's tenants, their projects, their team members, and the AI providers they connect to.

| Feature ID | Entity | File |
|---|---|---|
| F-009 | Organization | `app/models/organization.py` |
| F-010 | Project | `app/models/project.py` |
| F-011 | Membership | `app/models/membership.py` |
| F-012 | ProviderConnection | `app/models/provider_connection.py` |

Each entity has a corresponding repository:

| Repository | File |
|---|---|
| OrganizationRepository | `app/repositories/organization_repository.py` |
| ProjectRepository | `app/repositories/project_repository.py` |
| MembershipRepository | `app/repositories/membership_repository.py` |
| ProviderConnectionRepository | `app/repositories/provider_connection_repository.py` |

A single Alembic migration creates all tables, indexes, constraints, and PostgreSQL enum types:

```
migrations/versions/20260629_0200_a3b4c5d6e7f8_ep03_core_domain_models.py
```

A bug was also discovered and fixed in `app/db/mixins.py`: `BaseModel.__init_subclass__` was using `getattr(cls, "__abstract__", False)` which follows Python's MRO and inherited `True` from `BaseModel`, preventing auto-index creation on concrete models. Fixed to `cls.__dict__.get("__abstract__", False)` which checks only the class's own attributes.

---

### Why It Was Implemented

The platform cannot do anything useful until it knows:

1. **Who owns the data** — the `Organization` is the tenant. Every piece of data in AI FinOps belongs to exactly one Organization. Without this, there is no multi-tenancy.
2. **What the data belongs to** — `Project` is the attribution unit. Every AI API call will eventually be attributed to a Project, which is how organizations see "our ML team spent $12,400 this month."
3. **Who has access** — `Membership` links a human (identified by email) to an Organization with a role. Without it, there's no authorization model.
4. **Which AI providers are configured** — `ProviderConnection` stores metadata about each AI provider a customer has set up. Without it, the ingestion and adapter workers have no configuration to read.

These four models are the load-bearing walls of the entire platform. Nothing else can be built without them.

---

### SDD Sections Satisfied

| SDD Section | What It Specifies | How EP-03 Satisfies It |
|---|---|---|
| §4.4 Conceptual Data Model | Organization→Projects→ProviderConnections, Organization→Memberships | All four entities created with correct FK relationships |
| §4.5 Logical Data Model | Organization (tenant root, active/suspended/deleted), Project (attribution unit), Provider Connection (credential by reference) | All lifecycle states and relationships implemented |
| §4.7 Index Strategy | FK indexes on every FK column; cursor+deleted indexes on all entities | 20 indexes total; cursor+deleted auto-created by mixin |
| §5.3.2 RBAC Roles | Owner, Admin, Billing/Finance, Member, Viewer, Service Account | OWNER, ADMIN, MEMBER, VIEWER implemented; others deferred |
| DP-6 | `org_id` mandatory on all data | `organization_id` present on every child entity |
| DP-7 | Soft delete for entities | `deleted_at`/`deleted_by` inherited on all four models |

---

### Business Problems These Models Solve

Without EP-03, the platform is an empty shell. These models unlock:

- **Multi-tenancy**: Multiple companies can use AI FinOps simultaneously, completely isolated from each other (every row carries `organization_id`).
- **Cost attribution**: AI spend can be attributed to a specific Project. "Which team spent the most on GPT-4?" becomes answerable.
- **Access control**: Membership gives RBAC roles to emails. "Only Alice (OWNER) can suspend the org" becomes enforceable.
- **Provider configuration**: The platform knows which AI providers an organization has set up, which is required before the ingestion adapters can start pulling usage data.

---

## Section 2 — Domain Driven Design (DDD)

### The Core Concepts, Explained Simply

Domain Driven Design is a way of organizing code to mirror the real-world problem it solves. Instead of thinking "what tables do I need?", DDD asks "what are the real things in this business, and how do they relate?"

Here are the key concepts:

---

#### Entity

An **Entity** is a thing that has an identity that survives over time. Two entities are different even if all their data is identical, because they have different IDs.

**Example:** Two organizations both named "Acme Corp" are different entities — one might be `org_01j9abc` and another `org_01j9def`. The name can change; the identity cannot.

In AI FinOps: `Organization`, `Project`, `Membership`, and `ProviderConnection` are all entities. They each have a UUID primary key (`id`) and persist across time.

---

#### Value Object

A **Value Object** is a thing that is defined entirely by its data. Two value objects with the same data are the same thing. Value objects have no separate identity.

**Example:** An email address is a value object. Two strings `"alice@example.com"` and `"alice@example.com"` are the same email address — you don't need an ID to distinguish them.

In AI FinOps: `OrganizationStatus.ACTIVE`, `MembershipRole.OWNER`, `ProjectEnvironment.PRODUCTION` are value objects implemented as Python enums. They have no ID — they ARE their value.

---

#### Aggregate

An **Aggregate** is a cluster of entities and value objects that are treated as a single unit for data changes. One entity in the cluster is the **Aggregate Root** — the only entry point for operations on the cluster.

**Example:** `Organization` is an Aggregate Root. You don't delete a `Membership` directly — you go through the Organization ("remove this member from this organization"). The Organization controls the consistency of everything beneath it.

In AI FinOps:
```
Organization (Aggregate Root)
  ├── Projects       (part of the Organization aggregate)
  ├── Memberships    (part of the Organization aggregate)
  └── ProviderConnections  (part of the Organization aggregate)
```

---

#### Repository

A **Repository** is a collection abstraction that hides the database. From the service layer's perspective, calling `org_repo.get(id)` feels like looking up an item in a dictionary — you don't know (or care) whether it hits PostgreSQL, a cache, or a mock.

In AI FinOps: `OrganizationRepository`, `ProjectRepository`, etc. are repositories. They translate domain operations ("give me the organization with this slug") into SQL queries.

---

#### Domain Model

A **Domain Model** is the set of objects that capture the real-world concepts of the business — entities, value objects, aggregates, and the rules between them. It is the heart of the application.

In AI FinOps: the domain model for this Epic is the four entities and their relationships. The domain model does NOT include REST controllers, database sessions, or HTTP responses. Those are infrastructure concerns.

---

#### Bounded Context

A **Bounded Context** is a boundary within which a domain model applies. The same word can mean different things in different bounded contexts.

**Example:** "User" in the Identity context means a human principal with authentication credentials. "User" in the Analytics context might just mean `user_id` on a usage event. These are the same word for different concepts.

In AI FinOps (from SDD §3.5):

| Bounded Context | Owns |
|---|---|
| **Identity / Organization** | Organizations, Users, Projects, Memberships |
| **Provider** | ProviderConnections, Pricing |
| **Event / Ingestion** | UsageEvents, Costs, Adjustments |
| **Governance** | Budgets, Policies |
| **Analytics** | Rollups, Forecasts |

EP-03 implemented the **Identity / Organization** bounded context (Organizations, Projects, Memberships) and the beginning of the **Provider** context (ProviderConnections).

---

### Why These Are Domain Entities (Not Just Database Tables)

A common mistake is to confuse a database table with a domain entity. Here's why each of our four models qualifies as a true domain entity:

**Organization** — It has identity (`id`), lifecycle states (`ACTIVE → SUSPENDED → ARCHIVED`), business rules ("slug must be unique globally"), and relationships ("owns Projects, has Members"). A database table just stores rows; this entity has *meaning*.

**Project** — It has identity, it belongs to exactly one Organization (a business rule), it has an environment that classifies how it's used (DEVELOPMENT / STAGING / PRODUCTION), and it will serve as the attribution target for all AI usage. It exists in the domain as a *billing unit*.

**Membership** — It represents a *relationship* between a human and an Organization, with a *role* that grants permissions. It's not just a join table — it carries semantic meaning (the person is an OWNER, not just a foreign key pair).

**ProviderConnection** — It represents a *configured integration* with an AI provider. It's not a credentials record (credentials are in Secrets store) — it's the organizational declaration that "we use OpenAI here, and here's the metadata for how we use it."

---

## Section 3 — Every Model Explained

### Organization

**Purpose**: The top-level tenant entity. Everything in AI FinOps is owned by an Organization. It is the Aggregate Root for all tenant data.

**Responsibilities**:
- Serves as the top-level isolation boundary (DP-6: every record carries `org_id`)
- Owns the lifecycle of Projects, Memberships, and ProviderConnections
- Its slug is the human-readable identifier used in URLs and display
- Its status controls whether the tenant is active, suspended, or archived

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | UUID v7 | Yes (PK) | Auto-generated time-ordered UUID |
| `name` | String(255) | Yes | Display name ("Acme Corporation") |
| `slug` | String(100) | Yes, UNIQUE | URL-safe identifier ("acme-corp") |
| `description` | Text | No | Optional free-text |
| `website` | String(2048) | No | Organization website URL |
| `logo_url` | String(2048) | No | Logo image URL |
| `billing_email` | String(320) | No | Where invoices are sent |
| `status` | OrganizationStatus | Yes | ACTIVE / SUSPENDED / ARCHIVED |
| `created_at` | TIMESTAMPTZ | Yes | Set by PostgreSQL on INSERT |
| `updated_at` | TIMESTAMPTZ | Yes | Updated by PostgreSQL on every UPDATE |
| `deleted_at` | TIMESTAMPTZ | No | NULL = active; non-NULL = soft-deleted |
| `deleted_by` | UUID | No | Who deleted it (FK to users, deferred) |

**Relationships**:
- `projects` → 1:many with `Project` (CASCADE delete)
- `memberships` → 1:many with `Membership` (CASCADE delete)
- `provider_connections` → 1:many with `ProviderConnection` (CASCADE delete)

**Indexes**:

| Index | Columns | Purpose |
|---|---|---|
| `uq_organizations_slug` | `slug` UNIQUE | Enforces global slug uniqueness |
| `ix_organizations_slug` | `slug` | Fast slug lookups |
| `ix_organizations_status` | `status` | Filter active orgs by status |
| `ix_organizations_cursor` | `(created_at, id)` | Cursor-based pagination |
| `ix_organizations_deleted` | `deleted_at` | Fast active-record filtering |

**Soft Delete Behavior**: `deleted_at IS NULL` = active. When soft-deleted, `deleted_at` is set to the current UTC timestamp and `deleted_by` records who did it. The repository's `_active_query()` always filters `WHERE deleted_at IS NULL`, so soft-deleted orgs are invisible to normal queries. Hard-delete is available but should only be used in admin/test contexts.

**Example Data**:
```
id:            01jz4f2b-0000-7000-8000-000000000001
name:          "Stripe Inc."
slug:          "stripe"
status:        ACTIVE
billing_email: "finops@stripe.com"
created_at:    2026-01-15 09:00:00+00
deleted_at:    NULL
```

**Example Queries**:
```python
# Get org by slug (used in API routes)
org = await org_repo.get_by_slug("stripe")

# Check if slug is already taken before creating
if await org_repo.slug_exists("stripe"):
    raise ValueError("Slug already taken")

# List all ACTIVE orgs (first page)
page = await org_repo.list_by_status(OrganizationStatus.ACTIVE, limit=20)
```

---

### Project

**Purpose**: The cost attribution unit. Every AI API call will eventually resolve to a Project. "Which project spent the most?" is the core analytics query this model enables.

**Responsibilities**:
- Groups AI usage for reporting and budgeting
- Is always scoped to exactly one Organization (DP-6)
- Carries an `environment` tag to separate development/staging/production costs
- Will be the attribution target for all Usage Events (EP-05+)

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | UUID v7 | Yes (PK) | |
| `organization_id` | UUID | Yes (FK) | Parent Organization |
| `name` | String(255) | Yes | "ML Platform", "Customer Chat" |
| `description` | Text | No | |
| `environment` | ProjectEnvironment | Yes | DEVELOPMENT / STAGING / PRODUCTION |
| `created_at`, `updated_at` | TIMESTAMPTZ | Yes | Auto-managed |
| `deleted_at`, `deleted_by` | TIMESTAMPTZ / UUID | No | Soft-delete |

**Relationships**:
- `organization` → many:1 with `Organization`
- `provider_connections` → 1:many with `ProviderConnection` (SET NULL on project delete)

**Indexes**:

| Index | Columns | Purpose |
|---|---|---|
| `ix_projects_org_id` | `organization_id` | FK index; fast "list all projects for org" |
| `ix_projects_environment` | `environment` | Filter by env |
| `ix_projects_org_env` | `(organization_id, environment)` | "List all production projects for this org" |
| `ix_projects_cursor` | `(created_at, id)` | Pagination |
| `ix_projects_deleted` | `deleted_at` | Active-record filter |

**Soft Delete**: Projects are soft-deleted independently of their Organization. A project can be soft-deleted (archived) while the Organization remains active. If the Organization is hard-deleted, the CASCADE on the FK deletes the Projects too.

**Example Data**:
```
id:              01jz4f2b-0000-7000-8000-000000000010
organization_id: 01jz4f2b-0000-7000-8000-000000000001  (Stripe)
name:            "Customer Support Chat"
environment:     PRODUCTION
created_at:      2026-02-01 10:00:00+00
```

**Example Queries**:
```python
# List all projects for an org (paginated)
page = await proj_repo.list_by_org(org_id, limit=20)

# List only PRODUCTION projects
page = await proj_repo.list_by_org_and_env(
    org_id,
    ProjectEnvironment.PRODUCTION,
)

# How many projects does this org have?
count = await proj_repo.count_by_org(org_id)
```

---

### Membership

**Purpose**: The RBAC relationship between a human (identified by email) and an Organization. Controls what a person is allowed to do.

**Responsibilities**:
- Assigns a role to a user within a specific Organization
- Allows the same email to have different roles in different Organizations
- Will be the basis for authorization checks in EP-04+
- Acts as the future anchor between "email" and a `User` record (when Users are implemented)

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | UUID v7 | Yes (PK) | |
| `organization_id` | UUID | Yes (FK) | Parent Organization |
| `user_email` | String(320) | Yes | Identity anchor |
| `role` | MembershipRole | Yes | OWNER / ADMIN / MEMBER / VIEWER |
| `created_at`, `updated_at` | TIMESTAMPTZ | Yes | Auto-managed |
| `deleted_at`, `deleted_by` | TIMESTAMPTZ / UUID | No | Soft-delete |

**Why email, not user_id?** There is no Users table yet. EP-03 deliberately avoids implementing authentication (per the stop condition). Email is the correct MVP anchor — it's stable, unique, and familiar. When EP-04 adds Users, a migration will add `user_id` as a FK alongside (or replacing) `user_email`.

**Roles and What They Mean**:

| Role | Who is it? | Typical permissions |
|---|---|---|
| OWNER | Founder, Account Manager | Everything, including deleting the org |
| ADMIN | Engineering Lead, Finance Lead | Manage projects, providers, budgets, members |
| MEMBER | Engineer, Data Scientist | Create projects, submit ingestion, read analytics |
| VIEWER | Stakeholder, Read-only Finance | Read everything, change nothing |

**Constraints**:
- `UNIQUE(organization_id, user_email)` — one person can only have one active role per org. If they need multiple roles (unlikely), they would need a soft-deleted old membership + new one.

**Indexes**:

| Index | Columns | Purpose |
|---|---|---|
| `uq_memberships_org_email` | `(organization_id, user_email)` UNIQUE | Prevents duplicate membership |
| `ix_memberships_org_id` | `organization_id` | "List all members of this org" |
| `ix_memberships_email` | `user_email` | "Which orgs does alice@example.com belong to?" |
| `ix_memberships_role` | `role` | "List all owners of this org" |
| `ix_memberships_cursor` | `(created_at, id)` | Pagination |
| `ix_memberships_deleted` | `deleted_at` | Active-record filter |

**Example Data**:
```
id:              01jz4f2b-0000-7000-8000-000000000020
organization_id: 01jz4f2b-0000-7000-8000-000000000001  (Stripe)
user_email:      "alice@stripe.com"
role:            OWNER
created_at:      2026-01-15 09:01:00+00

id:              01jz4f2b-0000-7000-8000-000000000021
organization_id: 01jz4f2b-0000-7000-8000-000000000001  (Stripe)
user_email:      "bob@stripe.com"
role:            ADMIN
```

**Example Queries**:
```python
# Is alice an owner of this org?
m = await mem_repo.get_by_org_and_email(org_id, "alice@stripe.com")
if m and m.role == MembershipRole.OWNER:
    allow_action()

# Which orgs does alice belong to?
page = await mem_repo.list_by_email("alice@stripe.com")

# List all owners of this org
page = await mem_repo.list_by_org_and_role(org_id, MembershipRole.OWNER)
```

---

### ProviderConnection

**Purpose**: Records that an Organization has configured a specific AI provider. Stores non-secret metadata only. Credentials live elsewhere (Secrets store, §4.15).

**Responsibilities**:
- Tells the platform "this org uses OpenAI" (or Anthropic, Google, etc.)
- Optionally scoped to a specific Project (for project-level provider configurations)
- Provides the `configuration` JSONB bag for non-sensitive metadata (base URLs, rate limits, model aliases)
- Will be the configuration source for Adapter Workers (EP-05+) that pull usage data from providers

**Security rule (critical)**: `configuration` is a JSONB column for **non-secret** metadata only. API keys, tokens, and credentials must NEVER be stored here. They belong in the Secrets store (KMS-backed, encrypted). This is enforced by code review, not by the schema itself.

**Fields**:

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | UUID v7 | Yes (PK) | |
| `organization_id` | UUID | Yes (FK) | Parent Organization |
| `project_id` | UUID | No (FK, nullable) | Optional project scope |
| `provider_name` | String(255) | Yes | Internal name ("openai-prod") |
| `display_name` | String(255) | Yes | Human name ("OpenAI Production") |
| `provider_type` | ProviderType | Yes | OPENAI / ANTHROPIC / etc. |
| `is_active` | Boolean | Yes | Whether this connection is enabled |
| `configuration` | JSONB | Yes | Non-secret metadata dict |
| `created_at`, `updated_at` | TIMESTAMPTZ | Yes | Auto-managed |
| `deleted_at`, `deleted_by` | TIMESTAMPTZ / UUID | No | Soft-delete |

**Provider Types and Why They Exist**:

| ProviderType | Notes |
|---|---|
| OPENAI | GPT-4, GPT-4o, Whisper, embeddings |
| ANTHROPIC | Claude 3/4 family |
| GROK | xAI Grok models |
| GOOGLE | Gemini family |
| AZURE_OPENAI | Azure-hosted OpenAI endpoints |
| OPENROUTER | Multi-provider routing gateway |
| OLLAMA | Local/self-hosted models |

**project_id: Why nullable?** A connection can be org-wide (applies to all projects) or project-specific (only for that project's API calls). An org might have one "global OpenAI" connection and one "ML team Anthropic" connection scoped to a specific project.

**Indexes**:

| Index | Columns | Purpose |
|---|---|---|
| `ix_provider_connections_org_id` | `organization_id` | "List all connections for this org" |
| `ix_provider_connections_project_id` | `project_id` | "List connections for this project" |
| `ix_provider_connections_type` | `provider_type` | "List all OpenAI connections" |
| `ix_provider_connections_org_active` | `(organization_id, is_active)` | "List all ACTIVE connections for this org" (hot path for adapters) |
| `ix_provider_connections_cursor` | `(created_at, id)` | Pagination |
| `ix_provider_connections_deleted` | `deleted_at` | Active-record filter |

**Example Data**:
```
id:              01jz4f2b-0000-7000-8000-000000000030
organization_id: 01jz4f2b-0000-7000-8000-000000000001  (Stripe)
project_id:      NULL  (org-wide)
provider_name:   "openai-global"
display_name:    "OpenAI (Global)"
provider_type:   OPENAI
is_active:       true
configuration:   {
                   "base_url": "https://api.openai.com/v1",
                   "rate_limit_rpm": 10000
                 }
```

---

## Section 4 — Every Relationship Explained

### One-to-Many (1:many)

A **one-to-many** relationship means one record on the "one" side is associated with multiple records on the "many" side.

```
Organization (one)
    │
    ├──── Project (many)
    ├──── Membership (many)
    └──── ProviderConnection (many)
```

In code, the "many" side always holds the foreign key. So `projects.organization_id` points back to `organizations.id` — NOT the other way around.

In SQLAlchemy, you declare both sides:

```python
# Organization side ("one") — has a list
projects: Mapped[list[Project]] = relationship("Project", back_populates="organization")

# Project side ("many") — has a single ref
organization: Mapped[Organization] = relationship("Organization", back_populates="projects")
```

---

### Many-to-One (many:1)

**Many-to-one** is the same relationship viewed from the other direction.

`Project → Organization` is many-to-one: many projects belong to one organization.

The FK (`organization_id`) always lives on the "many" side.

---

### Foreign Keys

A **Foreign Key (FK)** is a column in one table that references the primary key of another table. It enforces referential integrity: you cannot insert a row into `projects` with an `organization_id` that doesn't exist in `organizations`.

In SQLAlchemy:
```python
organization_id: Mapped[uuid.UUID] = mapped_column(
    PG_UUID(as_uuid=True),
    ForeignKey("organizations.id", ondelete="CASCADE", name="fk_projects_organization_id"),
    nullable=False,
)
```

- `"organizations.id"` — references the `id` column of the `organizations` table
- `ondelete="CASCADE"` — what happens in the database when the parent is deleted
- `name=...` — explicit constraint name for migrations (critical for Alembic downgrade)

---

### ON DELETE CASCADE

**CASCADE** means: "if the parent row is deleted, automatically delete all child rows."

```
Delete Organization "Stripe"
    → Automatically deletes all Projects for Stripe
    → Automatically deletes all Memberships for Stripe
    → Automatically deletes all ProviderConnections for Stripe
```

This is the behavior for **hard** deletion only. In normal operations, we use **soft delete** — so CASCADE never fires in production. But if you need to truly destroy an organization in a test cleanup or admin operation, CASCADE ensures no orphan rows remain.

**Why CASCADE (not RESTRICT)?** RESTRICT would prevent you from deleting an Organization if any Projects exist. That would make test cleanup painful and admin operations require manual ordering. CASCADE is the correct choice here because Projects/Memberships/Connections have no meaning without their Organization.

---

### ON DELETE SET NULL

**SET NULL** means: "if the parent row is deleted, set the FK column to NULL (don't delete the child)."

This is used for `ProviderConnection.project_id → projects.id`:

```
Delete Project "Customer Chat"
    → ProviderConnections that pointed to this project
      get project_id = NULL
    → They become org-scoped connections (still exist)
    → Nothing is lost
```

This is correct because a ProviderConnection is owned by the Organization, not the Project. It makes sense for it to survive when a project is removed.

---

### Unique Constraints

A **Unique Constraint** enforces that a column (or combination of columns) cannot have duplicate values.

| Constraint | Table | Columns | Business Rule |
|---|---|---|---|
| `uq_organizations_slug` | organizations | `slug` | No two orgs can have the same slug |
| `uq_memberships_org_email` | memberships | `(organization_id, user_email)` | One person can only have one active membership per org |

The `uq_memberships_org_email` is a **composite unique constraint** — the combination must be unique. Alice can have one membership in Stripe and one in Acme (same email, different orgs). But she can't have two memberships in Stripe.

---

### Composite Indexes

A **composite index** covers multiple columns together. It makes queries faster when ALL indexed columns appear in the WHERE clause.

**Example: `ix_projects_org_env` on `(organization_id, environment)`**

This index makes the following query fast:
```sql
SELECT * FROM projects
WHERE organization_id = $1
AND environment = 'production'
AND deleted_at IS NULL;
```

Without the composite index, PostgreSQL would have to scan all rows for the org, then filter by environment. With the index, it jumps directly to the matching rows.

**Important rule**: The column ORDER in a composite index matters. `(organization_id, environment)` accelerates queries that filter on `organization_id` first. It does NOT accelerate queries that filter only on `environment` (with no org filter).

---

### Relationship Loading: Lazy vs Eager

When you access `org.projects` in Python, SQLAlchemy has to load those records from the database. **When** does it do this?

**Lazy loading** (`lazy="select"` — our default):
```python
org = await session.get(Organization, org_id)
# No query for projects yet...
projects = org.projects  # ← THIS fires a SELECT query right now
```

Lazy loading fires a new query when you first access the relationship. This is fine for most cases. However, it can cause the **N+1 problem**: if you have 100 organizations and access `org.projects` on each, you fire 100 + 1 = 101 queries.

**Eager loading** (not configured yet, but used with `options(selectinload(Organization.projects))`):
```python
stmt = select(Organization).options(selectinload(Organization.projects))
result = await session.execute(stmt)
# Both orgs AND projects loaded in 2 queries total
```

Eager loading fetches relationships upfront, avoiding N+1. The service layer will choose between lazy and eager loading based on what the API endpoint needs.

**Why we chose `lazy="select"` for now**: It's the safest default. It never fetches more than you need. The service layer (EP-04+) will add eager loading where N+1 would be a problem.

---

### Future Scalability of Relationships

At 10 users, relationship loading doesn't matter. At 1 million users:

- **Lazy loading of `org.memberships`** on 10,000 orgs → 10,001 queries → catastrophic
- **Eager loading + pagination** → 2 queries, handles any scale
- **Denormalized counts** → store `member_count` on Organization for dashboards (avoid loading all members just to count them)

These optimizations are not needed now. They are tracked as tech debt for when the platform scales.

---

### Relationship Diagram

```
┌─────────────────────────────────────┐
│            organizations            │
│─────────────────────────────────────│
│ id (PK)                             │
│ name, slug (UNIQUE), status         │
│ created_at, updated_at              │
│ deleted_at, deleted_by              │
└──────────┬─────────┬────────────────┘
           │         │             │
        1:many    1:many        1:many
           │         │             │
           ▼         ▼             ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│   projects   │ │ memberships  │ │  provider_connections │
│──────────────│ │──────────────│ │──────────────────────│
│ id (PK)      │ │ id (PK)      │ │ id (PK)              │
│ org_id (FK)  │ │ org_id (FK)  │ │ org_id (FK)          │
│ name         │ │ user_email   │ │ project_id (FK,NULL) │
│ environment  │ │ role         │ │ provider_type        │
│ soft-delete  │ │ soft-delete  │ │ is_active            │
└──────────────┘ └──────────────┘ │ configuration (JSONB)│
       │                          │ soft-delete          │
       │ 1:many (SET NULL)        └──────────────────────┘
       └──────────────────────────────────────────────┘
```

---

## Section 5 — SQLAlchemy Relationships: Teaching Guide

SQLAlchemy is the Python library that translates Python objects into SQL and back. Understanding it deeply is essential for contributing to AI FinOps.

### How SQLAlchemy Works: The Big Picture

```
Python Object          SQLAlchemy             PostgreSQL
─────────────────      ─────────────          ─────────────────
org = Organization()   ──translates──▶        INSERT INTO organizations
org.name = "Stripe"                           VALUES ('Stripe', ...)
await session.flush()
```

SQLAlchemy tracks every Python object you create. When you call `flush()`, it converts the Python object state into SQL and sends it to the database. When you call `commit()`, the transaction is made permanent.

---

### `relationship()`

`relationship()` tells SQLAlchemy that two models are connected. It creates a Python attribute that, when accessed, loads the related records.

```python
# In Organization model
projects: Mapped[list[Project]] = relationship(
    "Project",              # Which model to load
    back_populates="organization",  # The reverse side on Project
    cascade="all, delete-orphan",   # Cascade behavior
    lazy="select",          # Load on first access (lazy)
)
```

- `"Project"` — string reference, resolved lazily. This avoids circular imports.
- `back_populates="organization"` — the name of the reverse attribute on `Project`. SQLAlchemy needs both sides to sync them in memory.
- `cascade="all, delete-orphan"` — when an Organization is deleted in Python (via `session.delete(org)`), also delete all its projects. This is the Python-level cascade (separate from the DB-level `ondelete="CASCADE"`).
- `lazy="select"` — only load projects when you access `org.projects`.

---

### `back_populates`

`back_populates` keeps both ends of a relationship synchronized in the Python object graph. Without it, if you set `project.organization = org`, the `org.projects` list would not be updated automatically.

```python
# Organization side
projects: Mapped[list[Project]] = relationship(
    "Project",
    back_populates="organization",  # ← name of the attr on Project
)

# Project side
organization: Mapped[Organization] = relationship(
    "Organization",
    back_populates="projects",  # ← name of the attr on Organization
)
```

When you set `project.organization = some_org`, SQLAlchemy automatically adds `project` to `some_org.projects`. This bi-directional sync only works in memory (not across different sessions).

---

### `ForeignKey`

`ForeignKey` is a column constraint, not a relationship. It tells SQLAlchemy (and PostgreSQL) that this column references a specific column in another table.

```python
organization_id: Mapped[uuid.UUID] = mapped_column(
    PG_UUID(as_uuid=True),
    ForeignKey(
        "organizations.id",       # table.column reference
        ondelete="CASCADE",       # DB-level delete behavior
        name="fk_projects_organization_id",  # named for migrations
    ),
    nullable=False,
)
```

`ForeignKey` and `relationship()` are separate concepts:
- `ForeignKey` = the column that stores the reference (lives in the DB)
- `relationship()` = Python convenience to navigate between objects (lives in Python)

---

### `Mapped[]`

`Mapped[T]` is the SQLAlchemy 2.x type annotation that tells both SQLAlchemy and your type checker what type a column holds.

```python
name: Mapped[str] = mapped_column(String(255), nullable=False)
description: Mapped[str | None] = mapped_column(Text, nullable=True)
status: Mapped[OrganizationStatus] = mapped_column(...)
projects: Mapped[list[Project]] = relationship(...)
project: Mapped[Project | None] = relationship(...)
```

- `Mapped[str]` — a non-nullable string column
- `Mapped[str | None]` — a nullable string column (maps to `NULL` in SQL)
- `Mapped[list[Project]]` — a one-to-many relationship (returns a list)
- `Mapped[Project | None]` — a many-to-one or optional relationship

The `Mapped[]` annotation is Python 3.10+ style. With `from __future__ import annotations`, these annotations are strings until evaluated, which prevents circular import errors.

---

### `mapped_column()`

`mapped_column()` is the SQLAlchemy 2.x way to define a column. It combines the Python type annotation with the SQL column definition.

```python
slug: Mapped[str] = mapped_column(
    String(100),        # SQL type: VARCHAR(100)
    nullable=False,     # NOT NULL constraint
)

status: Mapped[OrganizationStatus] = mapped_column(
    SQLEnum(OrganizationStatus, name="organization_status", create_type=True),
    nullable=False,
    default=OrganizationStatus.ACTIVE,        # Python-level default
    server_default=OrganizationStatus.ACTIVE.value,  # SQL-level default
)
```

- `default=` — used by Python when you create a new object (before flush)
- `server_default=` — used by PostgreSQL when INSERT doesn't provide the value

---

### `Enum` (SQLAlchemy + PostgreSQL)

When you use `SQLEnum(MyPythonEnum, name="...", create_type=True)`, SQLAlchemy creates a **PostgreSQL custom type** (a real `CREATE TYPE` in the DB).

```sql
-- PostgreSQL creates this:
CREATE TYPE organization_status AS ENUM ('active', 'suspended', 'archived');

-- Then uses it as a column type:
ALTER TABLE organizations ADD COLUMN status organization_status NOT NULL DEFAULT 'active';
```

The Python enum is `str, enum.Enum` — it inherits from `str` so that the enum value IS a string. This means:
- `OrganizationStatus.ACTIVE == "active"` → `True`
- You can use them in string comparisons
- JSON serialization works automatically

```python
class OrganizationStatus(str, enum.Enum):
    ACTIVE = "active"       # Python name = ACTIVE, DB value = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"
```

---

### `JSONB`

`JSONB` is a PostgreSQL-specific column type that stores JSON in a binary format. It's faster to query than `JSON` and supports indexing.

```python
configuration: Mapped[dict[str, Any]] = mapped_column(
    JSONB,
    nullable=False,
    default=dict,                            # Python default: empty dict
    server_default=text("'{}'::jsonb"),      # SQL default: empty JSON object
)
```

In Python, you read and write it like a normal Python dictionary:
```python
conn.configuration["base_url"] = "https://api.openai.com/v1"
conn.configuration["rate_limit"] = 10000
```

SQLAlchemy serializes it to JSON when writing and deserializes from JSON when reading.

**JSONB vs JSON**: `JSONB` stores the binary representation (faster reads, supports indexing). `JSON` stores the raw text (faster writes, preserves key order). For a metadata field that you might query with operators like `->` or `@>`, JSONB is correct.

---

### How SQLAlchemy Translates a Python Object to a SQL Table

Here is the complete translation for `Organization`:

```python
# Python definition
class Organization(BaseModel):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[OrganizationStatus] = mapped_column(
        SQLEnum(OrganizationStatus, name="organization_status"),
        nullable=False,
        server_default="active",
    )
```

```sql
-- PostgreSQL result
CREATE TABLE organizations (
    id          UUID NOT NULL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(100) NOT NULL,
    status      organization_status NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ,
    deleted_by  UUID,
    CONSTRAINT uq_organizations_slug UNIQUE (slug)
);
CREATE INDEX ix_organizations_slug ON organizations (slug);
CREATE INDEX ix_organizations_status ON organizations (status);
CREATE INDEX ix_organizations_cursor ON organizations (created_at, id);
CREATE INDEX ix_organizations_deleted ON organizations (deleted_at);
```

---

## Section 6 — Repository Pattern (Advanced)

### Why Does BaseRepository Exist?

Without `BaseRepository`, every model would need its own implementation of: `get()`, `create()`, `update()`, `soft_delete()`, `hard_delete()`, `list_page()`, `count()`. That's 7 methods × 4 models = 28 methods, all doing nearly the same thing.

`BaseRepository[T]` is a **generic** class parameterized on the model type. You define it once, and every repository inherits the full CRUD implementation:

```python
class BaseRepository(Generic[T]):
    model: type[T]  # Subclass sets this once

    async def get(self, id: uuid.UUID) -> T | None:
        stmt = self._active_query().where(self.model.id == id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ... 6 more methods inherited by every repository
```

The `_active_query()` method is the cornerstone:
```python
def _active_query(self) -> Select[tuple[T]]:
    return select(self.model).where(self.model.deleted_at.is_(None))
```

Every query in every repository automatically filters out soft-deleted records. No engineer can forget this — it's baked into the base.

---

### Why Does OrganizationRepository Exist?

`BaseRepository` handles generic CRUD. It doesn't know anything about Organizations specifically. It can get by ID, create, update, soft-delete — but it cannot answer:

- "Give me the organization with slug 'stripe'" — `get_by_slug()`
- "Is this slug already taken?" — `slug_exists()`
- "List all SUSPENDED organizations for the admin dashboard" — `list_by_status()`

These are **domain-specific queries**. They belong in `OrganizationRepository`.

```
BaseRepository[Organization]
    │
    │  get(), create(), update(), soft_delete(),
    │  hard_delete(), list_page(), count()
    │
    └──▶ OrganizationRepository
              │
              │  get_by_slug()
              │  slug_exists()
              └─  list_by_status()
```

---

### Why Generic CRUD Is Insufficient

Consider what a service layer needs to create an Organization:

1. Check the slug is unique → domain rule, not in base CRUD
2. Validate the slug format → domain rule
3. Create the org → `base.create()`
4. Create the initial owner Membership → `mem_repo.create()`
5. Maybe emit an event → domain logic

Step 1 requires `org_repo.slug_exists()`. The base class has no concept of slugs. You need the domain-specific repository.

---

### Why Domain-Specific Repository Methods Are Useful

**`get_by_slug(slug)`**:
- Every API route that identifies an org by slug (e.g., `/v1/organizations/stripe/projects`) needs this.
- Without it, every caller would have to write the filter logic themselves, potentially forgetting the `deleted_at IS NULL` check.

**`list_by_status(status)`**:
- Admin dashboards need "show me all SUSPENDED organizations."
- Uses `list_page()` with `extra_filters`, so pagination, cursor encoding, and active filtering are all inherited.

**`list_active_by_org(org_id)` (ProviderConnectionRepository)**:
- The Adapter Workers (EP-05+) will call this constantly to find which providers to poll.
- Uses a composite index `(organization_id, is_active)` for maximum query performance.

**`count_by_org(org_id)` (ProjectRepository)**:
- Used to display "12 projects" in the org dashboard without loading all projects.
- Much more efficient than `len(page.items)` when paginating.

---

### How Repositories Interact with SQLAlchemy Sessions

The session lifecycle follows this pattern:

```
FastAPI Request
    │
    ▼
get_session() [dependencies.py]   ← yields session, commits or rolls back
    │
    ▼
Service layer (EP-04+)            ← gets session via Depends()
    │
    ▼
OrganizationRepository(session)   ← passes session to repo
    │
    ▼
repo.create(org)                  ← session.add() + session.flush()
    │                              (writes to DB, but no commit yet)
    ▼
Back to get_session()             ← session.commit() on clean exit
                                   session.rollback() on exception
```

Key rules:
- Repositories **flush** (write to DB transaction buffer), never **commit** (make permanent)
- Committing is the responsibility of the caller (via `get_session()` in EP-02)
- This allows multiple repository operations in one atomic transaction

```python
# Service layer (future EP-04):
async def create_organization(session: AsyncSession, name: str, slug: str, owner_email: str):
    org_repo = OrganizationRepository(session)
    mem_repo = MembershipRepository(session)

    # Both operations are in the same transaction
    org = await org_repo.create(Organization(name=name, slug=slug))
    await mem_repo.create(Membership(organization_id=org.id, user_email=owner_email, role=MembershipRole.OWNER))

    # commit() happens automatically in get_session() when this function returns
```

---

## Section 7 — Alembic Migration for EP-03

### Why New Migrations Were Needed

EP-02 created an empty migration (`09c89dba8c85`) that only verified the pipeline. EP-03 created four real database tables. You need a migration because:

1. The database doesn't know about Python classes. It only knows SQL DDL.
2. Migrations are the audit trail of schema changes. Every change to the database is recorded, reproducible, and reversible.
3. Without migrations, different environments (local, staging, production) drift apart. With migrations, they all reach the same schema by running `alembic upgrade head`.

---

### How Alembic Generated the Schema

EP-03 used a **hand-written migration** (not autogenerate) because there is no live database to connect to during development. The migration was written to exactly match the SQLAlchemy models.

The dependency chain:
```
(none)
  ↑
09c89dba8c85   ← EP-02: empty initial migration
  ↑
a3b4c5d6e7f8   ← EP-03: four tables + enums + indexes
  ↑
(next EP-04 migration will go here)
```

When you run `alembic upgrade head`, it applies each migration in order. Alembic records the current revision in the `alembic_version` table in PostgreSQL.

---

### Enum Creation in Alembic

PostgreSQL enums must be created **before** the tables that use them. The migration does this explicitly:

```python
_org_status = postgresql.ENUM(
    "active", "suspended", "archived",
    name="organization_status",
    create_type=False,  # We'll call .create() manually
)

def upgrade() -> None:
    bind = op.get_bind()
    _org_status.create(bind, checkfirst=True)  # CREATE TYPE organization_status AS ENUM (...)
    # ... then create the table
```

`checkfirst=True` means "don't fail if the type already exists." This makes the migration re-runnable safely (idempotent).

---

### Foreign Keys in Alembic

Foreign keys are declared inside `create_table()` using `sa.ForeignKeyConstraint`:

```python
op.create_table(
    "projects",
    sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
    # ...
    sa.ForeignKeyConstraint(
        ["organization_id"],          # local columns
        ["organizations.id"],          # referenced table.column
        name="fk_projects_organization_id",  # named for clean downgrade
        ondelete="CASCADE",
    ),
)
```

Named constraints are critical for `downgrade()`. Without a name, Alembic cannot reliably drop the constraint across databases.

---

### Indexes in Alembic

Indexes are created after the table:

```python
op.create_index("ix_projects_org_id", "projects", ["organization_id"])
op.create_index("ix_projects_org_env", "projects", ["organization_id", "environment"])
```

For composite indexes, list all columns in order. Order matters (as explained in Section 4).

---

### Upgrade Flow

```
alembic upgrade head
    │
    ├── 1. Connect to PostgreSQL
    ├── 2. Read alembic_version table (or create it)
    ├── 3. Find current revision (09c89dba8c85)
    ├── 4. Find target revision (head = a3b4c5d6e7f8)
    ├── 5. Execute upgrade():
    │       CREATE TYPE organization_status AS ENUM (...)
    │       CREATE TYPE project_environment AS ENUM (...)
    │       CREATE TYPE membership_role AS ENUM (...)
    │       CREATE TYPE provider_type AS ENUM (...)
    │       CREATE TABLE organizations (...)
    │       CREATE INDEX ix_organizations_slug ON organizations (slug)
    │       CREATE INDEX ix_organizations_cursor ON organizations (created_at, id)
    │       [... 16 more indexes ...]
    │       CREATE TABLE projects (...)
    │       CREATE TABLE memberships (...)
    │       CREATE TABLE provider_connections (...)
    └── 6. UPDATE alembic_version SET version_num = 'a3b4c5d6e7f8'
```

---

### Downgrade Flow

```
alembic downgrade -1
    │
    ├── 1. Current revision: a3b4c5d6e7f8
    ├── 2. Target: one step back = 09c89dba8c85
    ├── 3. Execute downgrade():
    │       DROP TABLE provider_connections  ← last created, first dropped
    │       DROP TABLE memberships
    │       DROP TABLE projects
    │       DROP TABLE organizations          ← first created, last dropped
    │       DROP TYPE provider_type
    │       DROP TYPE membership_role
    │       DROP TYPE project_environment
    │       DROP TYPE organization_status
    └── 4. UPDATE alembic_version SET version_num = '09c89dba8c85'
```

Tables are dropped in **reverse dependency order**: if `projects` has a FK to `organizations`, you must drop `projects` before `organizations`.

---

### Rollback Strategy (SDD §4.13)

AI FinOps follows the **expand-contract** migration pattern:

1. **Expand**: Add new structure (tables, columns, indexes). Backward-compatible with old code.
2. **Switch**: Deploy new code that uses the new structure.
3. **Contract**: Remove old structure in a later release.

For EP-03, `upgrade()` is the expand step. If something goes wrong:
- **Option 1 (preferred)**: `alembic downgrade -1` rolls back the schema change. Works cleanly because the migration is the first real schema migration.
- **Option 2**: Fix forward — apply a new migration that corrects the problem. This is the right approach if production data exists.
- **Option 3 (last resort)**: Restore from PostgreSQL backup (WAL-based point-in-time recovery).

---

### How Future Migrations Will Evolve

EP-04 will add a `users` table and FKs from:
- `memberships.user_email` → will become `memberships.user_id` (or gain a `user_id` FK column alongside `user_email`)
- `organizations.deleted_by`, `projects.deleted_by`, etc. → will gain FK to `users.id`

Each EP adds a new migration that chains from the previous:

```
09c89dba8c85  (EP-02: empty)
    ↑
a3b4c5d6e7f8  (EP-03: four tables)
    ↑
[EP-04 revision]  (users table, FKs)
    ↑
[EP-05 revision]  (usage events, pricing)
```

---

## Section 8 — Database Design Review

### Normalization

The EP-03 schema follows **3rd Normal Form (3NF)**:
- Every table has a primary key (`id`)
- No non-key column depends on another non-key column
- No repeated groups

Example: `billing_email` lives on `Organization`, not `Membership`. This is correct — billing email is a property of the organization, not of any individual member.

**When to denormalize**: When query performance demands it. For example, a future optimization might store `project_count` on `Organization` to avoid a COUNT query on every dashboard render. That would be deliberate denormalization for performance.

---

### Why Organization Is the Tenant Root

Every data architecture decision stems from one principle: **every record belongs to exactly one Organization** (SDD §DP-6).

This is called **multi-tenancy by row isolation**. All tenants share the same database, but each row carries `organization_id`. The platform enforces that every query includes `WHERE organization_id = :org_id` (the repository does this via `extra_filters`).

Alternatives considered:
- **Schema per tenant** (each org gets its own PostgreSQL schema): Hard to maintain, hard to migrate, doesn't scale to many small tenants.
- **Database per tenant**: Expensive, operational nightmare.
- **Row isolation**: Simple, scales well, costs almost nothing.

The tradeoff: row isolation is only as strong as the code that enforces it. A bug that forgets `WHERE organization_id = :org_id` leaks data across tenants. This is why repositories always start from `_active_query()` and accept `extra_filters` — the org filter is always the caller's responsibility.

---

### Why Projects Belong to Organizations

Projects are the attribution unit. A "project" in AI FinOps is the business team or product area whose AI spending you want to track. It is NOT a software project.

The 1:many relationship (Organization → Projects) mirrors the business reality: one company (Acme Corp) has multiple teams (ML Platform, Customer Chat, Search). Each team's AI spending is tracked separately.

**Future**: Projects will also be scoped to API keys, so that an OpenAI API key is associated with a Project, and usage via that key is automatically attributed.

---

### Why Provider Connections Belong to Both Org and Project

A `ProviderConnection` can be:
- **Org-scoped** (`project_id IS NULL`): One OpenAI account for the whole company. All projects under it.
- **Project-scoped** (`project_id IS NOT NULL`): A dedicated Anthropic account just for the ML team's project.

This dual scope gives customers flexibility. Most will use org-scoped connections. Large enterprises may have per-project contracts with different providers.

---

### Why Membership Currently Uses Email

At EP-03, there is no Users table. Authentication and user management are deferred to EP-04.

Email is the correct MVP anchor because:
- It's stable (doesn't change often)
- It's the identity that humans naturally use to identify each other
- It matches how invitation flows work: "You've been invited to Acme Corp. Sign up with this email."
- It's what an IdP (identity provider) returns after OIDC login

The migration path to a Users table is straightforward:
1. EP-04 adds `users` table with `email` as unique
2. A migration adds `user_id UUID FK(users.id)` to `memberships`
3. A backfill script resolves `user_email → user_id`
4. `user_email` column is optionally retained for display

---

### Why `deleted_by` Has No FK Yet

`deleted_by` is supposed to record which user performed the deletion. But there is no `users` table to FK to. Adding a FK now would:
1. Require creating the Users table in EP-03 (violates the stop condition)
2. Or using an unconstrained UUID (loses referential integrity)

The current implementation uses option 2 — store the UUID, skip the FK constraint. This is documented as technical debt. The FK will be added in the EP-04 migration.

---

### Technical Debt

| Item | Priority | Description |
|---|---|---|
| `deleted_by` FK | High | Add `FOREIGN KEY (deleted_by) REFERENCES users(id) ON DELETE SET NULL` in EP-04 migration |
| `Membership.user_email` → `user_id` | High | Replace email anchor with FK to `users.id` in EP-04 |
| `Project` lifecycle states | Medium | SDD §4.5 defines active/archived; only `environment` is implemented. Add `status` field in future migration. |
| `configuration` JSONB validation | Medium | No enforcement that API keys are absent from JSONB; relies on code review and policy |
| Eager loading strategy | Medium | N+1 risk when service layer traverses relationships at scale |

---

## Section 9 — Architecture Review (Production Code Review)

### Strengths

**1. Consistent inheritance pattern**
All four models inherit from `BaseModel`, which ensures `id`, `created_at`, `updated_at`, `deleted_at`, `deleted_by`, and `external_id` are present on every entity without duplication. This is the single most important structural decision in the data layer.

**2. Auto-index creation via `__init_subclass__`**
The `BaseModel.__init_subclass__` hook automatically adds `ix_<table>_cursor (created_at, id)` and `ix_<table>_deleted (deleted_at)` to every concrete model. Developers cannot forget these indexes. This is production-safe behavior.

**3. Opaque cursor pagination**
All list endpoints use cursor-based pagination keyed on `(created_at, id)`. This is stable over inserts (offset pagination drifts when rows are inserted between pages). The cursor is base64-encoded JSON, opaque to callers.

**4. `deleted_by` on all entities**
Every soft-delete records who performed the action. At scale, this is essential for audit trails and GDPR compliance. Most codebases add this as an afterthought and pay migration costs.

**5. Named FK and constraint names**
All FK constraints and unique constraints have explicit names (`fk_projects_organization_id`, `uq_organizations_slug`). This is critical for reliable `alembic downgrade` and future schema evolution.

**6. No secrets in `configuration` JSONB**
The model docstring explicitly says "never put API keys here." Combined with code review, this prevents the most common credential leak pattern.

**7. `TYPE_CHECKING` imports for relationships**
All cross-model type hints use `if TYPE_CHECKING:` imports, avoiding circular imports at runtime. SQLAlchemy resolves relationship string references lazily, after all models are imported.

---

### Weaknesses and Technical Debt

**1. `slug_exists()` is not atomic**
```python
if await org_repo.slug_exists("stripe"):
    raise ValueError("Slug already taken")
org = await org_repo.create(org)
```
There is a race condition: two concurrent requests can both pass the `slug_exists()` check and both try to create an organization with the same slug. The database will enforce the `uq_organizations_slug` constraint and one will fail with an `IntegrityError`. The service layer (EP-04) must catch this and return a clean 409 Conflict.

**2. `configuration` JSONB is fully unconstrained**
Any Python dict can be written to `configuration`. There is no schema enforcement, no type validation, and no warning if someone stores a sensitive key. Future improvement: add a Pydantic validator in the service layer.

**3. Lazy loading default creates N+1 risk**
With `lazy="select"` on all relationships, accessing `org.projects` inside a loop fires one query per organization. The service layer must use `selectinload()` or `joinedload()` where this would be a problem.

**4. No `updated_at` trigger in PostgreSQL**
The `updated_at` column uses SQLAlchemy's `onupdate=func.now()`. This fires on Python-level ORM updates but NOT if you update the row directly with raw SQL (e.g., migrations, admin scripts). A proper production setup would add a PostgreSQL trigger to handle this.

**5. `deleted_by` with no FK**
As discussed — no referential integrity until the Users table exists.

---

### Performance Concerns

- `list_by_email()` on Membership does a full scan of `memberships` filtered by `user_email`. For a user with memberships in 5 orgs this is fine. For a user with 10,000 org memberships (unlikely but possible for service accounts), consider a compound index on `(user_email, deleted_at)`.
- `configuration` JSONB queries (`WHERE configuration @> '{"key": "value"}'`) require a GIN index if you ever query inside the JSON. Currently none is defined.

---

### Security Concerns

- **No row-level org isolation in SQL**: The database has no `ROW SECURITY` policy. Tenant isolation is enforced by the Python code (repositories always filter by org). A code bug that omits the org filter leaks cross-tenant data. Consider adding PostgreSQL Row Level Security (RLS) as an additional defense-in-depth layer in production.
- **`configuration` JSON**: If someone accidentally stores a credential here, it sits in plaintext in PostgreSQL. The `configuration` column should have an application-level Pydantic validator that rejects known credential patterns (keys matching `*_key`, `*_secret`, `*_token`).

---

### Scalability Concerns

See Section 11 for a detailed breakdown. Short summary: the current schema is appropriate for tens of thousands of organizations. Beyond that, indexes should be reviewed and caching should be introduced at the repository level.

---

## Section 10 — Production Readiness Review

### What Monitoring Should Exist?

Before deploying these models to production, the following must be in place:

**Database health**:
- PostgreSQL connection pool saturation (active connections / pool size)
- Query execution time P50/P95/P99 per table
- Dead tuple accumulation rate (indicates heavy UPDATE/DELETE on soft-delete)
- Index bloat percentage

**Application layer**:
- Repository method latency (instrument every async repo method)
- Cache hit ratio (when caching is added in EP-04+)
- Cursor pagination token decode failure rate (signals client bugs)

---

### What Metrics Should Prometheus Expose?

```
# Repository query latency
aifinops_repository_query_duration_seconds{repository="OrganizationRepository", method="get_by_slug"} histogram

# Soft delete operations
aifinops_soft_delete_total{table="organizations"} counter

# Active records per table
aifinops_active_records{table="organizations"} gauge
aifinops_active_records{table="projects"} gauge

# Pagination page size
aifinops_list_page_size{repository="ProjectRepository"} histogram
```

---

### What Logs Should Exist?

All logs must be structured (JSON) via `structlog`. No f-string log messages with embedded data.

```python
# Good
logger.info("organization.created", org_id=str(org.id), slug=org.slug)

# Bad
logger.info(f"Created org {org.id}")
```

Required log events:
- Organization created/updated/soft-deleted
- Membership created/updated/soft-deleted
- ProviderConnection created/toggled active/inactive
- `slug_exists()` collision (helps debug concurrent create races)

---

### What Alerts Should Exist?

| Alert | Condition | Severity |
|---|---|---|
| DB connection pool exhausted | `active_connections / pool_size > 0.9` for 2 min | Critical |
| Slow query | P95 query time > 500ms for 5 min | Warning |
| Repository error rate | Error rate > 1% for 5 min | Critical |
| High soft-delete rate | `soft_delete_total` spikes unexpectedly | Warning |

---

### Failure Scenarios and Recovery

**Scenario 1: Migration fails mid-run**

Alembic runs migrations in a transaction (PostgreSQL DDL is transactional). If `upgrade()` fails partway through, the entire migration is rolled back. PostgreSQL is returned to the state before the migration. No partial tables or orphan enums.

**Scenario 2: Organization accidentally soft-deleted**

Recovery: `UPDATE organizations SET deleted_at = NULL, deleted_by = NULL WHERE id = $1`. No data is lost. This can be done via a migration or admin script without downtime.

**Scenario 3: Duplicate slug race condition**

Two concurrent requests try to create "stripe". One wins, the other hits `IntegrityError: unique constraint uq_organizations_slug`. The service layer catches `IntegrityError` and returns `409 Conflict`. No data corruption.

**Scenario 4: Wrong `ondelete` behavior**

If a Project is deleted and ProviderConnections should have been deleted but were SET NULL (or vice versa), recovery requires:
1. A compensating migration to correct the FK behavior
2. A data fix script to clean up the incorrectly-preserved/deleted rows

This is why the FK behavior was carefully chosen (CASCADE for org-owned data, SET NULL for optional project references).

---

## Section 11 — Scalability Review

### At 10 Users

- Single PostgreSQL instance (no replicas needed)
- No caching needed
- All queries complete in <5ms
- No partition strategy required
- Index creation on empty tables is instant

The EP-03 schema is complete overkill at this scale, but it's correct for the long term.

---

### At 1,000 Users

- Organizations: ~50–200 rows
- Projects: ~500–2,000 rows
- Memberships: ~2,000–10,000 rows
- ProviderConnections: ~200–1,000 rows

All queries still complete in <10ms. Single PostgreSQL instance is fine. No caching needed. Cursor pagination keeps list endpoints fast even as data grows.

---

### At 100,000 Users

- Memberships table: ~500,000–2,000,000 rows
- `list_by_org()` remains fast (indexed on `organization_id`)
- `list_by_email()` for power users (service accounts in many orgs) may show latency
- `get_by_slug()` on organizations becomes a hot path — introduce a Redis cache for slug → org_id lookups

```python
# Future: cache slug lookups
async def get_by_slug(self, slug: str) -> Organization | None:
    cached = await redis.get(f"org:slug:{slug}")
    if cached:
        return Organization(**json.loads(cached))
    org = await self._db_get_by_slug(slug)
    if org:
        await redis.setex(f"org:slug:{slug}", 300, org.json())
    return org
```

---

### At 1 Million Users

- Memberships: 5M–20M rows — still manageable with proper indexes
- Organizations: 50K–200K rows — add read replicas; route `list_*` queries to replica
- **Write-heavy tables**: `memberships` and `provider_connections` see high INSERT rate
- Consider partitioning `memberships` by `organization_id` hash if single-tenant writes become a bottleneck
- Add connection pooling middleware (PgBouncer) between the app and PostgreSQL

---

### At 10 Million Users

- Memberships: 50M–200M rows — table scanning is dangerous
- Add **partial indexes** on `deleted_at IS NULL` for each table:
  ```sql
  CREATE INDEX ix_memberships_active_org
  ON memberships (organization_id)
  WHERE deleted_at IS NULL;
  ```
- Add **materialized views** for org-level statistics (member count, project count, connection count)
- Add **Redis caching layer** for organization metadata (name, slug, status) with 5-minute TTL
- Consider **read replicas** for all list operations
- Consider moving `memberships` to a separate microservice with its own database if RBAC checks become a cross-cutting bottleneck

---

### Where Bottlenecks Would Appear

| Scale | Bottleneck | Fix |
|---|---|---|
| 100K users | `get_by_slug()` on hot path | Redis cache with 5m TTL |
| 500K users | `list_by_email()` for service accounts | Compound index on `(user_email, deleted_at)` |
| 1M users | DB connection saturation | PgBouncer connection pooler |
| 5M users | Full-table queries at org level | Partitioning by org_id hash |
| 10M users | `memberships` size | Microservice split + dedicated DB |

---

### Future ClickHouse Integration

ClickHouse is for **Usage Events** (the high-volume append-only event stream), NOT for the entities implemented in EP-03. The EP-03 models are **Master Data** (Organizations, Projects, Memberships, ProviderConnections) — they are low-volume, relational, and transactional. PostgreSQL is the correct and permanent store for them.

The integration point will be: ClickHouse Usage Events carry `organization_id` and `project_id` as columns (denormalized for performance). Dashboards join aggregated event data from ClickHouse with org/project metadata from PostgreSQL.

---

## Section 12 — How EP-04 Builds on EP-03

### What Comes Next

EP-04 is the Identity, RBAC, and REST API Epic. It builds directly on EP-03's models.

```
EP-03 provided:          EP-04 adds:
────────────────         ──────────────────────────────────
Organization     ──▶     OrganizationService (business rules)
Project          ──▶     ProjectService
Membership       ──▶     Identity FK: user_email → user_id
ProviderConn     ──▶     ProviderConnectionService
                 ──▶     Users table (new entity)
                 ──▶     API keys table (new entity)
                 ──▶     REST endpoints: /v1/organizations, /v1/projects, etc.
                 ──▶     JWT authentication middleware
                 ──▶     RBAC authorization checks
```

### Which EP-03 Classes Will Be Reused

| EP-03 Class | How EP-04 Uses It |
|---|---|
| `Organization` | Loaded by `OrganizationService`, returned in REST responses |
| `OrganizationRepository` | Used by `OrganizationService`; `get_by_slug()` used in auth middleware to resolve org from token |
| `Project` | Loaded by `ProjectService`; used in attribution resolver |
| `ProjectRepository` | `list_by_org()` used in `GET /v1/projects` |
| `Membership` | Loaded to check RBAC role on every protected endpoint |
| `MembershipRepository` | `get_by_org_and_email()` used in auth middleware to get user's role |
| `ProviderConnection` | Configuration source for Adapter Workers |
| `ProviderConnectionRepository` | `list_active_by_org()` used by Adapter Workers |

### The Authorization Flow (preview of EP-04)

```
Request: GET /v1/projects
    │
    ▼
1. Auth Middleware: validate JWT → extract user_email + org_id
    │
    ▼
2. MembershipRepository.get_by_org_and_email(org_id, user_email)
    │   → Returns Membership(role=MEMBER)
    ▼
3. RBAC check: MEMBER has "projects:read" scope? → YES
    │
    ▼
4. ProjectRepository.list_by_org(org_id, limit=20)
    │
    ▼
5. Return paginated project list
```

Every step in this flow uses an EP-03 repository.

---

## Section 13 — Architecture Diagrams

### Organization Hierarchy

```
AI FinOps Platform
│
├── Organization: "Stripe Inc."
│   ├── Project: "Customer Support Chat" [PRODUCTION]
│   ├── Project: "ML Platform" [PRODUCTION]
│   ├── Project: "Data Science Experiments" [DEVELOPMENT]
│   │
│   ├── Membership: alice@stripe.com [OWNER]
│   ├── Membership: bob@stripe.com [ADMIN]
│   ├── Membership: carol@stripe.com [MEMBER]
│   │
│   ├── ProviderConnection: "OpenAI Global" [org-scoped, ACTIVE]
│   └── ProviderConnection: "Anthropic ML" [scoped to ML Platform, ACTIVE]
│
└── Organization: "Shopify"
    ├── Project: "Recommendations Engine" [PRODUCTION]
    ├── Membership: dave@shopify.com [OWNER]
    └── ProviderConnection: "OpenAI Shopify" [org-scoped, ACTIVE]
```

---

### Repository Pattern

```
                    ┌────────────────────────────────────┐
                    │         Service Layer (EP-04)       │
                    │  OrganizationService                │
                    │  ProjectService                     │
                    └─────────────┬──────────────────────┘
                                  │ calls
                    ┌─────────────▼──────────────────────┐
                    │       Repository Layer (EP-03)      │
                    │                                     │
                    │  OrganizationRepository             │
                    │    ├── get_by_slug()                │
                    │    └── list_by_status()             │
                    │                                     │
                    │  ProjectRepository                  │
                    │    ├── list_by_org()                │
                    │    └── count_by_org()               │
                    │                                     │
                    │  MembershipRepository               │
                    │    └── get_by_org_and_email()       │
                    │                                     │
                    │  ProviderConnectionRepository       │
                    │    └── list_active_by_org()         │
                    └─────────────┬──────────────────────┘
                                  │ inherits
                    ┌─────────────▼──────────────────────┐
                    │     BaseRepository[T] (EP-02)       │
                    │  get(), create(), update()          │
                    │  soft_delete(), hard_delete()       │
                    │  list_page(), count()               │
                    └─────────────┬──────────────────────┘
                                  │ uses
                    ┌─────────────▼──────────────────────┐
                    │   SQLAlchemy AsyncSession (EP-02)   │
                    └─────────────┬──────────────────────┘
                                  │
                    ┌─────────────▼──────────────────────┐
                    │     Neon PostgreSQL                  │
                    │  organizations / projects           │
                    │  memberships / provider_connections │
                    └────────────────────────────────────┘
```

---

### Request Lifecycle (Future EP-04 Preview)

```
Client
  │  HTTP POST /v1/organizations
  ▼
FastAPI Router
  │  validate request body (Pydantic)
  ▼
Auth Middleware
  │  validate JWT → (user_email, is_authenticated)
  ▼
Dependency Injection (get_session)
  │  open AsyncSession
  ▼
OrganizationService (EP-04)
  │  slug_exists()     ← OrganizationRepository
  │  create()          ← OrganizationRepository
  │  create owner      ← MembershipRepository
  ▼
get_session commits transaction
  ▼
Response: 201 Created {org_id, external_id, slug, ...}
  │
Client
```

---

### Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        organizations                             │
│  id (PK)  name  slug (UQ)  status  billing_email               │
│  created_at  updated_at  deleted_at  deleted_by                │
└──────┬─────────────────────────────────────────────────────────┘
       │                        │                      │
       │ FK (CASCADE)           │ FK (CASCADE)         │ FK (CASCADE)
       │                        │                      │
       ▼                        ▼                      ▼
┌────────────────┐   ┌─────────────────────┐  ┌──────────────────────┐
│    projects    │   │     memberships     │  │ provider_connections │
│  id (PK)       │   │  id (PK)            │  │  id (PK)             │
│  org_id (FK)◄──┘   │  org_id (FK)◄───── ┘  │  org_id (FK)◄────── ┘
│  name          │   │  user_email (UQ*)   │  │  project_id (FK,NULL)│
│  environment   │   │  role               │  │  provider_type       │
│  soft-delete   │   │  soft-delete        │  │  is_active           │
└───────┬────────┘   └─────────────────────┘  │  configuration(JSON) │
        │                                      │  soft-delete         │
        │ FK (SET NULL, optional)              └──────────────────────┘
        └──────────────────────────────────────────────┘
               (*UQ = UNIQUE on (org_id, user_email))
```

---

### Migration Lifecycle

```
Developer writes model                 SQLAlchemy ORM
  ┌─────────────────┐                 ┌──────────────────┐
  │ class Org(Base) │ ──describes──▶  │ Base.metadata    │
  │   __tablename__ │                 │ (table definitions│
  │   columns       │                 │  in memory)      │
  └─────────────────┘                 └──────────────────┘
                                               │
                                    manually written migration
                                               │
                                               ▼
  ┌──────────────────────────────────────────────────────┐
  │  migrations/versions/20260629_0200_a3b4c5d6e7f8.py   │
  │                                                      │
  │  upgrade()   → CREATE TABLE / CREATE INDEX           │
  │  downgrade() → DROP TABLE / DROP TYPE                │
  └──────────────────────────────────┬───────────────────┘
                                     │
                    alembic upgrade head
                                     │
                                     ▼
  ┌──────────────────────────────────────────────────────┐
  │               Neon PostgreSQL                        │
  │  organizations + projects + memberships              │
  │  + provider_connections                              │
  │  alembic_version = 'a3b4c5d6e7f8'                  │
  └──────────────────────────────────────────────────────┘
```

---

## Section 14 — Top 25 Things Every Engineer Should Understand

A new backend engineer joining AI FinOps should understand these 25 concepts before writing their first line of code.

1. **Every entity inherits from `BaseModel`** — all domain models in AI FinOps have `id` (UUID v7), `created_at`, `updated_at`, `deleted_at`, `deleted_by`, and `external_id` automatically. Never define these manually.

2. **UUIDs are v7 (time-ordered)** — UUIDs are not random. They encode the timestamp in the high bits, so they sort roughly by creation time. This makes the `(created_at, id)` cursor index extremely efficient for pagination.

3. **`external_id` is Stripe-style** — the public identifier for any entity is `{prefix}_{uuid.hex}` with no hyphens. `org_01jz4f2babc...` is an Organization's external ID. Never expose raw UUIDs to clients.

4. **Soft delete means `deleted_at IS NULL`** — active records always have `deleted_at = NULL`. The `_active_query()` method in `BaseRepository` always adds this filter. Never write a raw query without it.

5. **Repositories never commit** — repositories call `session.flush()` to write to the DB transaction buffer, but never `session.commit()`. Committing is the `get_session()` dependency's job. This enables atomic multi-repository operations.

6. **`organization_id` is on every entity** — DP-6: every record in AI FinOps belongs to exactly one Organization. If you're creating a new model and it doesn't have `organization_id`, ask why.

7. **Cursor pagination, never offset** — `list_page()` returns a `CursorPage` with an opaque `next_cursor` token. Offset pagination (`LIMIT 20 OFFSET 100`) is unstable when data is inserted between pages. Never use `OFFSET` for production lists.

8. **`BaseModel.__init_subclass__` auto-creates two indexes** — every concrete model automatically gets `ix_<table>_cursor (created_at, id)` and `ix_<table>_deleted (deleted_at)`. Check with `cls.__dict__.get("__abstract__", False)`, NOT `getattr()` which follows MRO.

9. **Enums are `str, enum.Enum`** — all status/type enums inherit from both `str` and `enum.Enum`. This means `OrganizationStatus.ACTIVE == "active"` is `True`. They serialize to plain strings in JSON.

10. **PostgreSQL enums are native types** — our Python enums become actual `CREATE TYPE` in PostgreSQL, not `VARCHAR` with check constraints. They're type-safe at the DB level. Adding a new enum value requires a DB migration.

11. **`configuration` JSONB is for non-secret metadata only** — provider API keys, tokens, and secrets NEVER go in `configuration`. They go in the Secrets store (future KMS). Code review must enforce this.

12. **FK constraints are named** — every FK and unique constraint has an explicit name in Alembic migrations (e.g., `fk_projects_organization_id`). Anonymous constraints cannot be reliably dropped in `alembic downgrade`.

13. **ON DELETE CASCADE is for parent-owned data** — if a child record cannot exist without its parent (Project without Org), use CASCADE. ON DELETE SET NULL is for optional references (ProviderConnection without Project).

14. **`TYPE_CHECKING` prevents circular imports** — model files import each other only inside `if TYPE_CHECKING:` blocks. At runtime, relationships use string references (`"Project"`) resolved lazily by SQLAlchemy. This is the correct pattern for cross-model type hints.

15. **`back_populates` is not optional** — every `relationship()` that has a reverse side must use `back_populates` pointing to the corresponding attribute name on the other model. Without it, in-memory sync breaks.

16. **Lazy loading creates N+1 risk** — the default `lazy="select"` fires a new DB query every time you access a relationship. The service layer (EP-04+) must use `selectinload()` or `joinedload()` when iterating over relationships.

17. **`slug_exists()` is not atomic** — checking and then creating a slug is subject to a race condition. The DB `uq_organizations_slug` constraint is the final safety net. The service layer must catch `IntegrityError` and return a clean 409.

18. **All timestamps are UTC** — every `DateTime(timezone=True)` column stores UTC timestamps (PostgreSQL `TIMESTAMPTZ`). Never store local time. All application code must use `datetime.now(tz=timezone.utc)`.

19. **The `alembic_version` table tracks schema state** — `alembic upgrade head` is safe to run multiple times. It checks the current version and only applies unapplied migrations. It is the source of truth for what schema the database has.

20. **Downgrade order matters** — in `downgrade()`, drop tables in reverse dependency order. `provider_connections` must be dropped before `projects` before `organizations` because of FK dependencies.

21. **`Membership.user_email` is temporary** — it's an MVP anchor. EP-04 will add `user_id` as a FK to `users.id`. Don't build systems that assume `user_email` is the permanent identity field.

22. **`deleted_by` has no FK yet** — the UUID stored in `deleted_by` has no referential integrity until the `users` table exists. Treat it as an informational field, not a guaranteed FK.

23. **The repository is the only way to access the DB** — never write raw SQLAlchemy queries in service files, API routes, or middleware. All DB access goes through repositories. This ensures consistent soft-delete filtering, pagination, and session management.

24. **Alembic is not just for creating tables** — every column rename, index change, constraint addition, and enum value addition requires a migration. Never modify the DB manually in staging or production.

25. **Scale comes from the index, not the query** — the difference between a 5ms query and a 5000ms query on a large table is almost always an index. Before adding any new query, verify that every column in the `WHERE` clause is indexed.

---

## Section 15 — Engineering Lessons Learned

### Good Decisions

**Inheritance over composition for mixins**
Using `class Organization(BaseModel)` ensures that every entity has the same base columns. This is simpler than composing with Protocol or Mixin composition patterns, and SQLAlchemy's declarative model is built for this.

**Named constraints everywhere**
Every FK, every unique constraint, every index has an explicit name. This adds 10 seconds of work when writing the model and saves hours when debugging Alembic downgrade failures in production.

**`str, enum.Enum` for all enums**
Inheriting from `str` means enums serialize cleanly to JSON without custom serializers. This was the right call — it simplifies FastAPI response schemas, Pydantic models, and logging.

**`TYPE_CHECKING` pattern**
Using `if TYPE_CHECKING:` imports for cross-model relationships avoids circular imports cleanly. This pattern should be used in every future model file.

**Discovering the `__init_subclass__` bug**
The bug where `getattr(cls, "__abstract__", False)` inherits `True` from `BaseModel` was caught by writing tests that verified index auto-creation. **Testing the infrastructure, not just the business logic, is valuable.**

**Cursor pagination from day one**
Designing cursor pagination into `BaseRepository` before any business models exist means every future entity gets it for free. Retrofitting pagination into an existing API is painful.

---

### Architecture Improvements Made

**Bug fix: `cls.__dict__.get()` over `getattr()`**
The `__init_subclass__` was silently broken for all concrete models. Indexes were NOT being auto-created on Organization, Project, Membership, or ProviderConnection. The fix used `cls.__dict__.get("__abstract__", False)` — checking only the class's own attributes, not the inherited ones.

This would have caused missing indexes in production, degrading query performance on active-record filters. The unit test that checked for `ix_organizations_cursor` caught it immediately.

---

### Trade-offs

| Decision | Trade-off |
|---|---|
| `email` as identity in Membership | Simple MVP; requires migration when Users table is added |
| No PostgreSQL Row Level Security | Simpler now; weaker defense-in-depth against code bugs |
| Lazy loading default | Simpler code; N+1 risk in service layer |
| `configuration` as JSONB (no schema) | Flexible; no validation protection against secrets |
| Manual migration (not autogenerate) | Precise control; requires careful matching to models |

---

### What Should Be Repeated in Future Epics

1. **Every entity inherits `BaseModel`** — no exceptions.
2. **Every new file has a docstring explaining purpose, owner, and security rules.**
3. **Named constraints in every migration.**
4. **Unit tests verify index and constraint presence on every model.**
5. **`TYPE_CHECKING` for cross-model imports.**
6. **Repository-first: no raw SQLAlchemy in service layer.**
7. **Test the infrastructure code, not just the business code.**

---

### What Should Be Avoided

1. **Anonymous FK constraints** — they create invisible migration debt.
2. **`getattr()` in `__init_subclass__`** — always use `cls.__dict__.get()` when checking class-level attributes to avoid MRO inheritance surprises.
3. **Secrets in JSONB columns** — enforce this in code review from day one.
4. **Committing in repositories** — creates unpredictable transaction boundaries.
5. **Offset pagination** — use cursor pagination for all list endpoints.

---

### Recommendations for EP-04

1. **Add the Users table** as a migration that references EP-03's revision. Add `user_id` FK to `memberships`. Add `deleted_by` FK to all tables.
2. **Add `OrganizationService` and `ProjectService`** as the first service-layer classes. Keep all business rules (slug validation, role enforcement, lifecycle checks) in the service layer, not the repository.
3. **Add JWT middleware** that calls `mem_repo.get_by_org_and_email()` to resolve the user's role. Cache the result (Redis) with a short TTL to avoid a DB hit on every request.
4. **Add `selectinload()`** wherever the API response includes nested objects (e.g., `GET /v1/organizations` includes a `project_count`).
5. **Add `IntegrityError` handling** in the service layer for slug uniqueness races.
6. **Add Pydantic validators** on the service layer that reject secrets patterns in `configuration` JSONB.
7. **Write integration tests** (marked `@pytest.mark.integration`) that use a real PostgreSQL test database to verify FK CASCADE behavior, cursor pagination stability, and soft-delete filtering end-to-end.

---

_End of EP-03 Knowledge Transfer Document._

_For questions about this document or the EP-03 implementation, refer to the source code in `backend/app/models/`, `backend/app/repositories/`, `backend/migrations/versions/20260629_0200_a3b4c5d6e7f8_ep03_core_domain_models.py`, and `backend/tests/test_models_ep03.py`._
