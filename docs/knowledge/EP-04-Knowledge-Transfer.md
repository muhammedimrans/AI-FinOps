# EP-04 / EP-04.1 Knowledge Transfer — Users & Identity Foundation

| Field | Value |
|---|---|
| **Epic** | EP-04 — Users & Identity Foundation |
| **Sub-Epic** | EP-04.1 — Gap Closure |
| **Status** | Complete |
| **Author** | Principal Backend Engineer / AI FinOps |
| **Date** | 2026-06-29 |
| **Audience** | New and existing backend engineers |
| **Prerequisites** | EP-01 (Repository Foundation), EP-02 (Database Infrastructure), EP-03 / EP-03.5 (Core Domain Models + Hardening) |
| **Feeds** | EP-05 (Authentication, RBAC, REST APIs) |

> **Purpose.** This document is the engineering knowledge transfer for EP-04 and its gap-closure sub-epic EP-04.1. It explains what was built, why it was built, and every design decision an engineer needs to understand before working on the authentication or user-management layer.

---

## Section 1 — What Was Implemented

EP-04 introduced the `User` entity as the identity anchor for all human actors in the platform. EP-04.1 closed the gaps identified in the post-merge verification report, bringing the implementation to full specification compliance.

### Feature Map

| Feature ID | Scope | Description |
|---|---|---|
| F-013 | EP-04 / EP-04.1 | User ORM entity with all required fields |
| F-014 | EP-04 | Membership refactor: `user_id` FK column |
| F-015 | EP-04 / EP-04.1 | UserRepository with all required methods |
| F-016 | EP-04 / EP-04.1 | User validation (email, display_name, username, locale, timezone) |

### Files Created / Modified

| File | Change |
|---|---|
| `app/models/user.py` | Created (EP-04); expanded with UserStatus, username, email_verified, last_login_at, timezone, locale (EP-04.1) |
| `app/models/__init__.py` | Added User and UserStatus exports |
| `app/models/membership.py` | Added user_id FK column and User relationship |
| `app/repositories/user_repository.py` | Created (EP-04); added get_by_username, username_exists, search_users, update_last_login, count_by_status (EP-04.1) |
| `app/repositories/__init__.py` | Added UserRepository export |
| `app/core/validators.py` | Added validate_user_email, validate_display_name (EP-04); added validate_username, validate_locale, validate_timezone (EP-04.1) |
| `migrations/versions/20260629_0500_b1c2d3e4f5a6_ep04_users_and_identity.py` | EP-04 migration: creates users table, adds memberships.user_id |
| `migrations/versions/20260629_0600_c3d4e5f6a7b8_ep04_1_user_identity_completion.py` | EP-04.1 migration: UserStatus enum, all missing columns |
| `tests/test_ep04.py` | 95 unit tests covering all features |

---

## Section 2 — The User Entity (F-013)

### Column Reference

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | UUID | No | uuid7() | Time-ordered UUIDv7 primary key |
| `email` | String(320) | No | — | Unique; RFC 5321 format |
| `username` | String(50) | Yes | NULL | Unique among non-NULL values; 3-50 chars |
| `display_name` | String(255) | No | — | UI-facing name; 1-255 chars |
| `status` | UserStatus | No | 'active' | Lifecycle state; see §2.1 |
| `email_verified` | Boolean | No | false | True after email verification link clicked |
| `avatar_url` | String(2048) | Yes | NULL | — |
| `bio` | Text | Yes | NULL | — |
| `timezone` | String(64) | Yes | NULL | IANA identifier; e.g. 'America/New_York' |
| `locale` | String(35) | Yes | NULL | BCP 47 tag; e.g. 'en-US' |
| `last_login_at` | DateTime(tz) | Yes | NULL | Updated by UserRepository.update_last_login() |
| `created_at` | DateTime(tz) | No | now() | From BaseModel / TimestampMixin |
| `updated_at` | DateTime(tz) | No | now() | From BaseModel / TimestampMixin; onupdate |
| `deleted_at` | DateTime(tz) | Yes | NULL | NULL = active; non-NULL = soft-deleted |
| `deleted_by` | UUID | Yes | NULL | Actor UUID who soft-deleted the record |

### 2.1 UserStatus Enum

```python
class UserStatus(enum.StrEnum):
    ACTIVE   = "active"    # email verified; full access
    INVITED  = "invited"   # invitation sent; not yet verified
    DISABLED = "disabled"  # account suspended by administrator
```

**Lifecycle:** `INVITED → ACTIVE → DISABLED`

- A new user created via invitation API is `INVITED`. The invitation flow (EP-05) sends a verification email.
- When the user clicks the verification link, `status → ACTIVE` and `email_verified → True`.
- An administrator can disable any user account: `status → DISABLED`.
- A disabled user cannot log in (enforced by the auth layer in EP-05).

This is a PostgreSQL native enum type (`user_status`), created in the EP-04.1 migration. Using a native enum type rather than a string column enforces the constraint at the database level.

### 2.2 Why `is_active` Was Replaced

The EP-04 initial implementation used `is_active: bool`. This was insufficient because:
- It cannot represent the `INVITED` intermediate state.
- The SDD (§4.4) explicitly specifies the lifecycle as `invited → active → disabled`.
- An `INVITED` user is neither fully active nor disabled, so a two-state boolean loses information.

EP-04.1 replaces the column with `UserStatus`. Backward compatibility is preserved through a Python property:

```python
@property
def is_active(self) -> bool:
    return self.status == UserStatus.ACTIVE

@is_active.setter
def is_active(self, value: bool) -> None:
    self.status = UserStatus.ACTIVE if value else UserStatus.DISABLED
```

Any code written against the original EP-04 boolean continues to work. New code should use `status` directly.

### 2.3 Username Field Design

`username` is nullable. This is intentional for the following reasons:
1. Existing `memberships` rows referencing users created before this Epic have no username.
2. The invitation flow (EP-05) may create a user with only an email; the username can be set during onboarding.
3. PostgreSQL unique constraints on nullable columns correctly allow multiple NULL values (each NULL is considered distinct per SQL standard).

The `uq_users_username` constraint prevents two users from claiming the same non-NULL username.

### 2.4 Timezone and Locale

Both fields are user preferences stored server-side:
- `timezone` is an IANA identifier (e.g. `UTC`, `America/New_York`). It is used by the reporting layer to format timestamps for the user. **All stored timestamps remain UTC.** See SDD §4.19.
- `locale` is a BCP 47 tag (e.g. `en`, `en-US`, `zh-Hans-CN`). It guides number and date formatting in reports and the UI.

Neither field affects how data is stored or indexed. They are pure presentation preferences.

---

## Section 3 — Membership Refactor (F-014)

### The Expand-Contract Pattern

Before EP-04, `Membership.user_email` was the only identity anchor. EP-04 introduced `user_id` as a nullable FK to `users.id`:

```
memberships.user_id → users.id (ON DELETE CASCADE)
```

This follows the **Expand-Contract** (or **Parallel Change**) migration pattern:
1. **Expand**: Add `user_id` as nullable. Existing rows keep `user_email`; new code populates both.
2. **Contract** (future): Once the auth layer (EP-05) guarantees all rows have `user_id`, make the column NOT NULL and eventually deprecate `user_email`.

The column is nullable to preserve backward compatibility with rows that existed before EP-04. **Both `user_id` and `user_email` must be written for new rows** until the contract phase.

### Relationship Loading

```python
# In Membership
user: Mapped[User | None] = relationship("User", back_populates="memberships", lazy="raise")

# In User
memberships: Mapped[list[Membership]] = relationship(
    "Membership", back_populates="user",
    cascade="all, delete-orphan", lazy="raise", passive_deletes=True,
)
```

`lazy="raise"` is the project-wide policy (H-003 from EP-03.5). Accessing either relationship without an explicit `selectinload()` or `joinedload()` in the query raises `InvalidRequestError` immediately — it never silently issues synchronous SQL (which would crash the async event loop with `MissingGreenlet`).

`passive_deletes=True` on the User → Membership cascade tells SQLAlchemy not to load children into Python for orphan detection; the `ON DELETE CASCADE` constraint handles it at the database level.

---

## Section 4 — UserRepository (F-015)

### Method Reference

| Method | Returns | Notes |
|---|---|---|
| `get_by_email(email)` | `User \| None` | Filters deleted_at IS NULL |
| `get_by_username(username)` | `User \| None` | Filters deleted_at IS NULL |
| `email_exists(email, exclude_id=None)` | `bool` | SELECT EXISTS — no row hydration |
| `username_exists(username, exclude_id=None)` | `bool` | SELECT EXISTS — no row hydration |
| `list_active(limit, cursor, order)` | `CursorPage[User]` | status == ACTIVE only |
| `search_users(query, limit, cursor)` | `CursorPage[User]` | ILIKE on email, username, display_name |
| `count_active()` | `int` | status == ACTIVE |
| `count_by_status(status)` | `int` | Any UserStatus value |
| `update_last_login(user_id)` | `None` | Bulk UPDATE; sets last_login_at and updated_at |
| `create(instance)` | `User` | From BaseRepository |
| `get(id)` | `User \| None` | From BaseRepository |
| `get_or_raise(id)` | `User` | From BaseRepository |
| `update(instance, **kwargs)` | `User` | From BaseRepository |
| `soft_delete(instance, deleted_by)` | `User` | From BaseRepository |

### Why `update_last_login` Uses a Bulk UPDATE

The `update_last_login` method is called by the authentication flow on every login. Loading the full ORM row (via `get()`) just to set one timestamp is wasteful at high request rates. A targeted `UPDATE WHERE id = ?` is significantly cheaper:

```python
stmt = (
    sql_update(User)
    .where(User.id == user_id, User.deleted_at.is_(None))
    .values(last_login_at=now, updated_at=now)
)
await self._session.execute(stmt)
```

Note that `updated_at` is explicitly set because SQLAlchemy's `onupdate` hook only fires when a mapped ORM instance is modified via the ORM layer — it does not fire on bulk `execute()` statements.

### `search_users` Design

```python
pattern = f"%{query}%"
extra_filter = or_(
    User.email.ilike(pattern),
    User.username.ilike(pattern),
    User.display_name.ilike(pattern),
)
```

- Returns all non-deleted users regardless of `status` (admins may need to find INVITED or DISABLED users).
- Case-insensitive via PostgreSQL `ILIKE`.
- Paginated via the cursor mechanism — no `OFFSET` queries.
- For production scale, consider a `pg_trgm` GIN index on these three columns.

---

## Section 5 — Validators (F-016)

All validators are in `app/core/validators.py`. They are **pure functions** — no database I/O, no side effects.

### `validate_user_email(email: str) -> None`

Conservative RFC 5321 regex check. Full RFC 5322 parsing (with the `email-validator` library) is deferred to the API layer. This is the fast guard before any DB round-trip.

### `validate_display_name(display_name: str) -> None`

Rejects empty strings and strings exceeding 255 characters.

### `validate_username(username: str) -> None`

Rules:
- 3–50 characters
- Only: letters, digits, underscores (`_`), hyphens (`-`)
- Must start **and** end with a letter or digit
- Single-character names rejected (min 3)

### `validate_locale(locale: str) -> None`

Validates BCP 47 locale tags using a regex: `^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$`

Valid examples: `en`, `en-US`, `zh-Hans-CN`, `pt-BR`.

### `validate_timezone(timezone: str) -> None`

Validates IANA timezone identifiers using `zoneinfo.available_timezones()`.  
The set is cached at **module import time** to avoid repeated file I/O on every validation call.

Valid examples: `UTC`, `America/New_York`, `Europe/London`, `Asia/Tokyo`.

---

## Section 6 — Migrations

### Migration Chain

```
09c89dba8c85  initial_migration_pipeline_verification
      ↓
a3b4c5d6e7f8  ep03_core_domain_models
      ↓
b1c2d3e4f5a6  ep04_users_and_identity         ← EP-04 original
      ↓
c3d4e5f6a7b8  ep04_1_user_identity_completion  ← EP-04.1 gap closure
```

### EP-04 Migration (`b1c2d3e4f5a6`)

Creates:
- `users` table with initial columns (email, display_name, is_active, avatar_url, bio)
- `memberships.user_id` nullable FK column

### EP-04.1 Migration (`c3d4e5f6a7b8`) — Expand-Contract

Step-by-step to avoid locking or data loss:

1. `CREATE TYPE user_status AS ENUM ('active', 'invited', 'disabled')`
2. `ALTER TABLE users ADD COLUMN status user_status NULL`
3. `UPDATE users SET status = 'active' WHERE is_active = true`
4. `UPDATE users SET status = 'disabled' WHERE is_active = false`
5. `ALTER TABLE users ALTER COLUMN status SET NOT NULL`
6. `DROP INDEX ix_users_is_active` then `DROP COLUMN is_active`
7. Add columns: `username`, `email_verified`, `last_login_at`, `timezone`, `locale`
8. Add constraint `uq_users_username` and indexes `ix_users_username`, `ix_users_status`

The downgrade reverses every step. INVITED users are mapped back to `is_active = true` on downgrade (they are considered "pending active").

---

## Section 7 — What EP-05 Must Build On Top Of EP-04

| Item | Location | EP-05 Action |
|---|---|---|
| `UserStatus.INVITED` | `app/models/user.py` | Invitation endpoint sets status=INVITED; verification sets ACTIVE |
| `User.email_verified` | `app/models/user.py` | Verification flow sets True |
| `User.last_login_at` | `app/models/user.py` | Auth service calls `UserRepository.update_last_login()` |
| `validate_username()` | `app/core/validators.py` | Registration endpoint calls before persisting |
| `validate_locale()` | `app/core/validators.py` | Profile update endpoint calls before persisting |
| `validate_timezone()` | `app/core/validators.py` | Profile update endpoint calls before persisting |
| `Membership.user_id` | `app/models/membership.py` | Auth service populates when user is associated with an org |
| `lazy="raise"` policy | All relationships | Service layer must use `selectinload()` / `joinedload()` |
| Password hash / Argon2 | Not yet implemented | EP-05 adds `password_hash` column (separate migration) |
| JWT issuance | Not yet implemented | EP-05 auth service |
| Row-level security | Not yet implemented | EP-05 (TD-008) |

---

## Section 8 — Test Coverage

| Test Class | Tests | Covers |
|---|---|---|
| `TestUserModel` | 30 | All fields, UserStatus enum, is_active compat property, all indexes and constraints |
| `TestMembershipUserIdField` | 4 | FK column, index, default, set |
| `TestUserRepository` | 14 | All 11 methods including new EP-04.1 additions |
| `TestValidateUserEmail` | 10 | All branches of email validation |
| `TestValidateDisplayName` | 6 | All branches of display_name validation |
| `TestValidateUsername` | 14 | All branches of username validation |
| `TestValidateLocale` | 10 | All branches of locale validation |
| `TestValidateTimezone` | 9 | All branches of timezone validation |
| **Total** | **97** | Full unit coverage, no live database required |

All 298 tests in the suite pass (203 pre-existing + 95 new EP-04/EP-04.1 tests).
