# Backend Contract: Organization Context

**Status:** IMPLEMENTED — EP-12.1 (2026-06-30)  
**Endpoint:** `GET /v1/organizations`  
**Discovered:** EP-12 pre-implementation review (2026-06-30)  
**Temporary workaround:** ~~`OrgPrompt` component (manual UUID entry)~~ (removed)

---

## Problem

Every dashboard endpoint requires `organization_id: uuid.UUID` as a query
parameter:

```
GET /v1/dashboard/overview?organization_id=<uuid>&...
GET /v1/dashboard/time-series?organization_id=<uuid>&...
GET /v1/dashboard/providers?organization_id=<uuid>&...
GET /v1/dashboard/models?organization_id=<uuid>&...
GET /v1/dashboard/projects?organization_id=<uuid>&...
GET /v1/dashboard/organization?organization_id=<uuid>&...
GET /v1/dashboard/kpis?organization_id=<uuid>&...
```

The frontend has no way to know which UUID to send because:

1. **JWT payload** (`sub`, `jti`, `email`, `iat`, `exp`, `type`) — no org ID.
2. **`LoginResponse`** (`access_token`, `refresh_token`, `token_type`,
   `expires_in`, `user: UserPublic`) — no org membership.
3. **`UserPublic`** (`id`, `email`, `username`, `display_name`, `status`,
   `email_verified`) — no org membership.
4. **No endpoint exists** that returns the calling user's organization list.

The backend dashboard code acknowledges this: *"Org membership verification is
deferred to EP-11 — for now we validate the JWT and trust the organization_id
query parameter."*

---

## Required Backend Change

Add one of the following (Option A is preferred):

### Option A — Include memberships in LoginResponse (simplest)

Extend `UserPublic` and `LoginResponse` to include org memberships:

```python
class OrgMembership(BaseModel):
    organization_id: str   # UUID as string
    organization_name: str
    slug: str
    role: str              # "owner" | "admin" | "member" | "viewer"

class UserPublic(BaseModel):
    id: str
    email: str
    username: str | None
    display_name: str
    status: str
    email_verified: bool
    organizations: list[OrgMembership] = []   # ← ADD THIS
```

**Pros:** Zero extra round-trips. Frontend selects the first org (or shows a
picker for multi-org users) immediately after login.  
**Cons:** If a user's org memberships change while their session is active, the
list in the token/login response becomes stale. Acceptable for most FinOps use
cases where org changes are infrequent.

### Option B — New GET /v1/organizations endpoint

```
GET /v1/organizations
Authorization: Bearer <access_token>

Response 200:
[
  {
    "organization_id": "uuid",
    "organization_name": "Acme Corp",
    "slug": "acme-corp",
    "role": "admin"
  }
]
```

**Pros:** Always reflects current membership state.  
**Cons:** Requires an extra round-trip after login before any dashboard query
can be made.

---

## Frontend Impact Once Contract Is Delivered

1. Remove `frontend/src/components/OrgPrompt.tsx`  
2. In the login success handler (`Login.tsx`), call the new endpoint (Option B)
   or read `data.user.organizations` (Option A)  
3. If the user has exactly one org, auto-select it and set
   `useOrgStore.getState().setOrganization(id, name)`  
4. If the user has multiple orgs, show an org switcher UI before entering the
   dashboard  
5. All dashboard queries will fire automatically because `enabled: !!organizationId`
   in `useDashboard.ts` — no other changes needed

---

## Implementation (EP-12.1)

Option B was chosen. `GET /v1/organizations` was added in EP-12.1:

- **Endpoint:** `GET /v1/organizations/` (requires `Authorization: Bearer <token>`)
- **Backend:** `backend/app/api/v1/organizations.py`
- **Schema:** `backend/app/schemas/organizations.py` — `OrgMembershipItem`, `OrganizationsResponse`
- **Repository:** `MembershipRepository.list_by_user_email_with_orgs` — eager-loads Organization via `selectinload`, filters to ACTIVE orgs only
- **Frontend flow:** Login → `getOrganizations()` → if 1 org auto-select → navigate("/dashboard"); else `OrgSelector` component handles multi/empty states
- **`OrgPrompt` removed.** `OrgSelector` (in `frontend/src/components/OrgSelector.tsx`) replaces it with automatic org discovery.
- **Seed data:** `backend/scripts/seed_demo.py` creates Org "Zero Protocol" + User `admin@0protocol.net` / `Admin@123`
