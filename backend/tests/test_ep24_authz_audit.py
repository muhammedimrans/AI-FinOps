"""Tests for the EP-24 Authorization & Permission Consistency Audit.

Covers:
  - The general "create/write implies delete" consistency invariant across
    every resource's WRITE/DELETE permission pair (app.auth.rbac), guarding
    against a future resource reintroducing the Project bug this audit
    found and fixed.
  - PROJECT_DELETE now granted to MEMBER (the fix itself).
  - The documented exception (ORG_DELETE is OWNER-only despite ADMIN
    holding ORG_WRITE) stays exactly as documented — this test fails loudly
    if that exception is ever silently widened or narrowed without updating
    the comment in app/auth/rbac.py.

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import pytest

from app.auth.rbac import ROLE_PERMISSIONS, Permission, has_permission
from app.models.membership import MembershipRole

# WRITE/DELETE permission pairs that model a "create-then-later-delete-your-
# own-resource" flow — the shape the audit's consistency rule applies to.
# ORG is deliberately excluded: there is no ORG_CREATE action (workspaces
# are created implicitly at registration, never by a role's own choice), so
# the create-implies-delete rule has no "create" side to compare against —
# see the documented exception in app/auth/rbac.py.
_WRITE_DELETE_PAIRS: list[tuple[str, Permission, Permission]] = [
    ("project", Permission.PROJECT_WRITE, Permission.PROJECT_DELETE),
    ("provider connection", Permission.PROVIDER_WRITE, Permission.PROVIDER_DELETE),
]

_ALL_ROLES = [
    MembershipRole.OWNER,
    MembershipRole.ADMIN,
    MembershipRole.MEMBER,
    MembershipRole.VIEWER,
]


class TestPermissionConsistencyInvariant:
    """Any role that can WRITE (create/update) a resource must also be able
    to DELETE it — the rule this whole audit exists to enforce, encoded so
    it can never silently regress for Project, Provider Connection, or any
    future resource added to _WRITE_DELETE_PAIRS."""

    @pytest.mark.parametrize("resource,write_perm,delete_perm", _WRITE_DELETE_PAIRS)
    def test_write_implies_delete_for_every_role(
        self,
        resource: str,
        write_perm: Permission,
        delete_perm: Permission,
    ) -> None:
        for role in _ALL_ROLES:
            can_write = has_permission(role, write_perm)
            can_delete = has_permission(role, delete_perm)
            # write implies delete — a role need not be able to write to
            # delete (e.g. a hypothetical moderator role), but every role
            # that CAN create/update must also be able to remove what it
            # created.
            assert not can_write or can_delete, (
                f"{role.value} can {write_perm.value} but not {delete_perm.value} "
                f"for {resource} — inconsistent create/delete authorization."
            )


class TestProjectDeleteGrantedToMember:
    """The concrete fix: MEMBER held PROJECT_WRITE without PROJECT_DELETE."""

    def test_member_has_project_write(self) -> None:
        assert has_permission(MembershipRole.MEMBER, Permission.PROJECT_WRITE)

    def test_member_now_has_project_delete(self) -> None:
        assert has_permission(MembershipRole.MEMBER, Permission.PROJECT_DELETE)

    def test_viewer_still_cannot_write_or_delete_projects(self) -> None:
        assert not has_permission(MembershipRole.VIEWER, Permission.PROJECT_WRITE)
        assert not has_permission(MembershipRole.VIEWER, Permission.PROJECT_DELETE)


class TestProviderConnectionsRemainConsistent:
    """MEMBER has neither PROVIDER_WRITE nor PROVIDER_DELETE — a matched
    pair (both withheld), not a partial-permission gap, so this audit left
    it unchanged. Locks that in."""

    def test_member_has_neither(self) -> None:
        assert not has_permission(MembershipRole.MEMBER, Permission.PROVIDER_WRITE)
        assert not has_permission(MembershipRole.MEMBER, Permission.PROVIDER_DELETE)

    def test_admin_has_both(self) -> None:
        assert has_permission(MembershipRole.ADMIN, Permission.PROVIDER_WRITE)
        assert has_permission(MembershipRole.ADMIN, Permission.PROVIDER_DELETE)


class TestApiKeyWriteCoversRenameAndDelete:
    """Organization API keys have a single API_KEY_WRITE permission (no
    separate delete permission) — create, rename (PATCH), and revoke
    (DELETE) are all gated by the same permission by construction, so there
    is no create/delete split to audit for this resource."""

    def test_member_cannot_write_api_keys(self) -> None:
        assert not has_permission(MembershipRole.MEMBER, Permission.API_KEY_WRITE)

    def test_admin_can_write_api_keys(self) -> None:
        assert has_permission(MembershipRole.ADMIN, Permission.API_KEY_WRITE)


class TestOrganizationDeleteDocumentedException:
    """ORG_DELETE is intentionally OWNER-only even though ADMIN holds
    ORG_WRITE (can rename/describe a workspace) — the one deliberate,
    documented exception to the audit's consistency rule, because deleting
    an organization cascades to every project/connection/key/member it owns
    and is categorically more destructive than any other delete in this
    table. This test pins the exception so it can't silently drift."""

    def test_admin_can_write_but_not_delete_org(self) -> None:
        assert has_permission(MembershipRole.ADMIN, Permission.ORG_WRITE)
        assert not has_permission(MembershipRole.ADMIN, Permission.ORG_DELETE)

    def test_only_owner_can_delete_org(self) -> None:
        for role in _ALL_ROLES:
            expected = role == MembershipRole.OWNER
            assert has_permission(role, Permission.ORG_DELETE) is expected


class TestRolePermissionsMonotonic:
    """Sanity check that ROLE_PERMISSIONS still forms a strict hierarchy —
    each role's permission set is a superset of the role below it — since
    the audit's fixes only ever widen MEMBER, never touch OWNER/ADMIN/
    VIEWER, and a hierarchy break would indicate a typo in the fix."""

    def test_owner_is_superset_of_admin(self) -> None:
        assert ROLE_PERMISSIONS[MembershipRole.ADMIN] <= ROLE_PERMISSIONS[MembershipRole.OWNER]

    def test_admin_is_superset_of_member(self) -> None:
        assert ROLE_PERMISSIONS[MembershipRole.MEMBER] <= ROLE_PERMISSIONS[MembershipRole.ADMIN]

    def test_member_is_superset_of_viewer(self) -> None:
        assert ROLE_PERMISSIONS[MembershipRole.VIEWER] <= ROLE_PERMISSIONS[MembershipRole.MEMBER]
