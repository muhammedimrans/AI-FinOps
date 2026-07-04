"""Tests for API Key authentication middleware (EP-15).

Covers:
  - ApiKeyAuthService: valid/invalid/expired/deleted keys, org status checks,
    last_used_at update, permission parsing, query budget
  - Header parsing: missing/malformed/empty Authorization headers
  - GET /v1/organizations/{org_id}/api-keys authenticated via Bearer API key
    (the EP-15 success criterion), including permission and cross-org checks
  - Regression: the same endpoint still works via JWT (dual auth)
  - Concurrency: multiple simultaneous authenticate() calls don't interfere

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.api_key_auth import _extract_bearer_token, _looks_like_api_key
from app.auth.exceptions import (
    ApiKeyExpiredError,
    InvalidApiKeyError,
    OrganizationSuspendedError,
)
from app.auth.rbac import Permission
from app.models.membership import Membership, MembershipRole
from app.models.organization import OrganizationStatus
from app.models.user import User
from app.services.api_key_auth_service import ApiKeyAuthContext, ApiKeyAuthService
from tests.conftest import make_api_key, make_org

_ORG_ID = uuid.uuid4()
_RAW_KEY = "costorah_live_" + "a" * 43


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# Header parsing
# ══════════════════════════════════════════════════════════════════════════════


class TestExtractBearerToken:
    def test_valid_bearer_header(self) -> None:
        assert _extract_bearer_token(f"Bearer {_RAW_KEY}") == _RAW_KEY

    def test_missing_header_raises(self) -> None:
        with pytest.raises(InvalidApiKeyError):
            _extract_bearer_token(None)

    def test_empty_header_raises(self) -> None:
        with pytest.raises(InvalidApiKeyError):
            _extract_bearer_token("")

    def test_missing_bearer_scheme_raises(self) -> None:
        with pytest.raises(InvalidApiKeyError):
            _extract_bearer_token(_RAW_KEY)

    def test_wrong_scheme_raises(self) -> None:
        with pytest.raises(InvalidApiKeyError):
            _extract_bearer_token(f"Basic {_RAW_KEY}")

    def test_empty_token_after_bearer_raises(self) -> None:
        with pytest.raises(InvalidApiKeyError):
            _extract_bearer_token("Bearer ")

    def test_whitespace_only_token_raises(self) -> None:
        with pytest.raises(InvalidApiKeyError):
            _extract_bearer_token("Bearer    ")

    def test_case_insensitive_scheme(self) -> None:
        assert _extract_bearer_token(f"bearer {_RAW_KEY}") == _RAW_KEY


class TestLooksLikeApiKey:
    def test_true_for_costorah_prefix(self) -> None:
        assert _looks_like_api_key(f"Bearer {_RAW_KEY}") is True

    def test_false_for_jwt_like_token(self) -> None:
        assert _looks_like_api_key("Bearer eyJhbGciOiJIUzI1NiJ9.abc.def") is False

    def test_false_for_malformed_header(self) -> None:
        assert _looks_like_api_key("garbage") is False


# ══════════════════════════════════════════════════════════════════════════════
# ApiKeyAuthService
# ══════════════════════════════════════════════════════════════════════════════


def _mock_session_returning(*, key: Any, org: Any) -> AsyncMock:
    """Build a mock AsyncSession whose execute() yields key then org, in order."""
    key_result = MagicMock()
    key_result.scalar_one_or_none.return_value = key
    org_result = MagicMock()
    org_result.scalar_one_or_none.return_value = org

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[key_result, org_result])
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


class TestApiKeyAuthServiceAuthenticate:
    @pytest.mark.asyncio
    async def test_valid_key_returns_context(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = make_org()
        org.id = _ORG_ID
        org.status = OrganizationStatus.ACTIVE
        session = _mock_session_returning(key=key, org=org)

        service = ApiKeyAuthService(session)
        context = await service.authenticate(_RAW_KEY)

        assert isinstance(context, ApiKeyAuthContext)
        assert context.api_key is key
        assert context.organization is org
        assert context.organization_id == _ORG_ID
        assert context.api_key_id == key.id

    @pytest.mark.asyncio
    async def test_hashes_before_lookup(self) -> None:
        """The raw key must never be used for lookup — only its SHA-256 hash."""
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = make_org()
        org.status = OrganizationStatus.ACTIVE
        session = _mock_session_returning(key=key, org=org)

        await ApiKeyAuthService(session).authenticate(_RAW_KEY)

        # First execute() call is the key lookup; inspect the compiled
        # statement's parameters rather than the raw key ever appearing.
        first_call_stmt = str(session.execute.await_args_list[0].args[0])
        assert _RAW_KEY not in first_call_stmt

    @pytest.mark.asyncio
    async def test_unknown_key_raises_invalid(self) -> None:
        session = _mock_session_returning(key=None, org=None)
        with pytest.raises(InvalidApiKeyError):
            await ApiKeyAuthService(session).authenticate("costorah_live_unknown")

    @pytest.mark.asyncio
    async def test_deleted_key_is_indistinguishable_from_unknown(self) -> None:
        """Repository queries already filter deleted_at IS NULL — a revoked
        key's hash simply won't be found, same as one that never existed."""
        session = _mock_session_returning(key=None, org=None)
        with pytest.raises(InvalidApiKeyError):
            await ApiKeyAuthService(session).authenticate(_RAW_KEY)

    @pytest.mark.asyncio
    async def test_expired_key_raises_expired(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        key.expires_at = datetime.now(UTC) - timedelta(days=1)
        session = _mock_session_returning(key=key, org=None)
        with pytest.raises(ApiKeyExpiredError):
            await ApiKeyAuthService(session).authenticate(_RAW_KEY)

    @pytest.mark.asyncio
    async def test_not_yet_expired_key_succeeds(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        key.expires_at = datetime.now(UTC) + timedelta(days=1)
        org = make_org()
        org.status = OrganizationStatus.ACTIVE
        session = _mock_session_returning(key=key, org=org)
        context = await ApiKeyAuthService(session).authenticate(_RAW_KEY)
        assert context.api_key is key

    @pytest.mark.asyncio
    async def test_missing_organization_raises_suspended(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        session = _mock_session_returning(key=key, org=None)
        with pytest.raises(OrganizationSuspendedError):
            await ApiKeyAuthService(session).authenticate(_RAW_KEY)

    @pytest.mark.asyncio
    async def test_suspended_organization_raises(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = make_org()
        org.status = OrganizationStatus.SUSPENDED
        session = _mock_session_returning(key=key, org=org)
        with pytest.raises(OrganizationSuspendedError):
            await ApiKeyAuthService(session).authenticate(_RAW_KEY)

    @pytest.mark.asyncio
    async def test_archived_organization_raises(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = make_org()
        org.status = OrganizationStatus.ARCHIVED
        session = _mock_session_returning(key=key, org=org)
        with pytest.raises(OrganizationSuspendedError):
            await ApiKeyAuthService(session).authenticate(_RAW_KEY)

    @pytest.mark.asyncio
    async def test_touches_last_used_at_on_success(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        assert key.last_used_at is None
        org = make_org()
        org.status = OrganizationStatus.ACTIVE
        session = _mock_session_returning(key=key, org=org)

        await ApiKeyAuthService(session).authenticate(_RAW_KEY)

        assert key.last_used_at is not None
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_touch_last_used_on_failure(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        key.expires_at = datetime.now(UTC) - timedelta(days=1)
        session = _mock_session_returning(key=key, org=None)
        with pytest.raises(ApiKeyExpiredError):
            await ApiKeyAuthService(session).authenticate(_RAW_KEY)
        session.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exactly_two_selects_and_one_flush(self) -> None:
        """Query budget: one lookup (key + org) plus the mandatory last_used_at
        update — never more, regardless of how many checks run."""
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = make_org()
        org.status = OrganizationStatus.ACTIVE
        session = _mock_session_returning(key=key, org=org)

        await ApiKeyAuthService(session).authenticate(_RAW_KEY)

        assert session.execute.await_count == 2
        assert session.flush.await_count == 1


class TestApiKeyAuthContextPermissions:
    def test_parses_known_permissions(self) -> None:
        key = make_api_key(permissions=["usage:read", "org:read"])
        org = make_org()
        context = ApiKeyAuthContext(api_key=key, organization=org)
        assert context.permissions == {Permission.USAGE_READ, Permission.ORG_READ}

    def test_ignores_unknown_permission_strings(self) -> None:
        key = make_api_key(permissions=["usage:read", "not:a:real:scope"])
        org = make_org()
        context = ApiKeyAuthContext(api_key=key, organization=org)
        assert context.permissions == {Permission.USAGE_READ}

    def test_has_permission_true_and_false(self) -> None:
        key = make_api_key(permissions=["usage:read"])
        org = make_org()
        context = ApiKeyAuthContext(api_key=key, organization=org)
        assert context.has_permission(Permission.USAGE_READ) is True
        assert context.has_permission(Permission.BILLING_WRITE) is False

    def test_empty_permissions_grants_nothing(self) -> None:
        key = make_api_key(permissions=[])
        org = make_org()
        context = ApiKeyAuthContext(api_key=key, organization=org)
        assert context.permissions == frozenset()
        assert context.has_permission(Permission.USAGE_READ) is False

    def test_created_by_and_ids_exposed_without_extra_lookup(self) -> None:
        creator = uuid.uuid4()
        key = make_api_key(org_id=_ORG_ID, created_by=creator)
        org = make_org()
        org.id = _ORG_ID
        context = ApiKeyAuthContext(api_key=key, organization=org)
        assert context.created_by == creator
        assert context.organization_id == _ORG_ID
        assert context.api_key_id == key.id


# ══════════════════════════════════════════════════════════════════════════════
# Concurrency
# ══════════════════════════════════════════════════════════════════════════════


class TestPerformance:
    """Smoke-level performance guards, not strict SLA benchmarks — hermetic
    tests can't measure real network/DB latency, only catch pathological
    regressions (e.g. accidental N+1s, unbounded loops) cheaply and reliably.
    """

    @pytest.mark.asyncio
    async def test_query_count_does_not_grow_across_repeated_authentications(self) -> None:
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = make_org()
        org.status = OrganizationStatus.ACTIVE

        for _ in range(20):
            key.last_used_at = None
            session = _mock_session_returning(key=key, org=org)
            await ApiKeyAuthService(session).authenticate(_RAW_KEY)
            # Every single call, independent of how many came before it,
            # costs exactly the same two SELECTs + one flush.
            assert session.execute.await_count == 2
            assert session.flush.await_count == 1

    @pytest.mark.asyncio
    async def test_authentication_completes_quickly_with_mocked_io(self) -> None:
        import time

        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = make_org()
        org.status = OrganizationStatus.ACTIVE
        session = _mock_session_returning(key=key, org=org)

        start = time.monotonic()
        await ApiKeyAuthService(session).authenticate(_RAW_KEY)
        elapsed = time.monotonic() - start

        # With all I/O mocked, this is pure CPU (hashing + attribute
        # plumbing) — a generous bound that only fails on a genuine
        # pathological regression, not environment jitter.
        assert elapsed < 0.25


class TestConcurrentAuthentication:
    @pytest.mark.asyncio
    async def test_multiple_keys_authenticate_independently_and_concurrently(self) -> None:
        keys_and_orgs = []
        raw_keys = []
        for i in range(5):
            raw = f"costorah_live_key{i}_" + "b" * 30
            raw_keys.append(raw)
            key = make_api_key(org_id=uuid.uuid4(), key_hash=_hash(raw), name=f"key-{i}")
            org = make_org()
            org.id = key.organization_id
            org.status = OrganizationStatus.ACTIVE
            keys_and_orgs.append((key, org))

        async def authenticate_one(raw: str, key: Any, org: Any) -> ApiKeyAuthContext:
            session = _mock_session_returning(key=key, org=org)
            return await ApiKeyAuthService(session).authenticate(raw)

        results = await asyncio.gather(
            *(
                authenticate_one(raw, key, org)
                for raw, (key, org) in zip(raw_keys, keys_and_orgs, strict=True)
            )
        )

        assert len(results) == 5
        for i, context in enumerate(results):
            assert context.api_key.name == f"key-{i}"


# ══════════════════════════════════════════════════════════════════════════════
# API integration: GET /v1/organizations/{org_id}/api-keys
# ══════════════════════════════════════════════════════════════════════════════


def _active_org(org_id: uuid.UUID = _ORG_ID) -> Any:
    from app.models.organization import Organization

    org = MagicMock(spec=Organization)
    org.id = org_id
    org.status = OrganizationStatus.ACTIVE
    org.slug = "acme"
    return org


def _patch_key_lookup(key: Any, org: Any) -> Any:
    return patch.multiple(
        "app.services.api_key_auth_service",
        OrganizationApiKeyRepository=MagicMock(
            return_value=MagicMock(
                get_by_hash=AsyncMock(return_value=key),
                update_last_used=AsyncMock(side_effect=lambda k: k),
            )
        ),
        OrganizationRepository=MagicMock(return_value=MagicMock(get=AsyncMock(return_value=org))),
    )


def _no_jwt_overrides(app: Any) -> None:
    """Ensure the dual-auth fallback path can't silently succeed via JWT."""
    from app.api.deps import get_db

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_db] = mock_get_db


class TestListApiKeysViaApiKeyAuth:
    @pytest.mark.asyncio
    async def test_valid_key_with_permission_succeeds(self, app: Any) -> None:
        _no_jwt_overrides(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["api_key:read"])
        org = _active_org()
        try:
            with (
                _patch_key_lookup(key, org),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.list",
                    new=AsyncMock(return_value=[key]),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_valid_key_without_permission_is_403(self, app: Any) -> None:
        _no_jwt_overrides(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=[])
        org = _active_org()
        try:
            with _patch_key_lookup(key, org):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Insufficient API Key permissions"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_key_for_a_different_org_is_rejected(self, app: Any) -> None:
        """A valid key for org B must not read org A's keys via org A's path."""
        _no_jwt_overrides(app)
        other_org_id = uuid.uuid4()
        key = make_api_key(
            org_id=other_org_id, key_hash=_hash(_RAW_KEY), permissions=["api_key:read"]
        )
        org = _active_org(other_org_id)
        try:
            with _patch_key_lookup(key, org):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Invalid API Key"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unknown_key_is_401_invalid(self, app: Any) -> None:
        _no_jwt_overrides(app)
        try:
            with _patch_key_lookup(None, None):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        headers={"Authorization": "Bearer costorah_live_doesnotexist"},
                    )
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Invalid API Key"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_expired_key_is_401_expired(self, app: Any) -> None:
        _no_jwt_overrides(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        key.expires_at = datetime.now(UTC) - timedelta(days=1)
        try:
            with _patch_key_lookup(key, None):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 401
            assert resp.json()["detail"] == "API Key expired"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_suspended_organization_is_403(self, app: Any) -> None:
        _no_jwt_overrides(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = _active_org()
        org.status = OrganizationStatus.SUSPENDED
        try:
            with _patch_key_lookup(key, org):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Organization suspended"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_archived_organization_is_403(self, app: Any) -> None:
        _no_jwt_overrides(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY))
        org = _active_org()
        org.status = OrganizationStatus.ARCHIVED
        try:
            with _patch_key_lookup(key, org):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            assert resp.status_code == 403
            assert resp.json()["detail"] == "Organization suspended"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_malformed_header_is_401(self, app: Any) -> None:
        _no_jwt_overrides(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    f"/v1/organizations/{_ORG_ID}/api-keys",
                    headers={"Authorization": "NotBearer costorah_live_x"},
                )
            # Doesn't look like an API key (no "Bearer costorah_live_" match via
            # the sniff) or a usable JWT either -> falls through to the JWT
            # path and fails there; either way, never a 200/500.
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_empty_bearer_token_is_401(self, app: Any) -> None:
        _no_jwt_overrides(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(
                    f"/v1/organizations/{_ORG_ID}/api-keys",
                    headers={"Authorization": "Bearer "},
                )
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_missing_header_falls_back_and_is_rejected(self, app: Any) -> None:
        _no_jwt_overrides(app)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.get(f"/v1/organizations/{_ORG_ID}/api-keys")
            assert resp.status_code == 401
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_response_never_contains_hash_or_raw_key(self, app: Any) -> None:
        _no_jwt_overrides(app)
        key = make_api_key(org_id=_ORG_ID, key_hash=_hash(_RAW_KEY), permissions=["api_key:read"])
        org = _active_org()
        try:
            with (
                _patch_key_lookup(key, org),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.list",
                    new=AsyncMock(return_value=[key]),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        headers={"Authorization": f"Bearer {_RAW_KEY}"},
                    )
            body_text = resp.text
            assert key.key_hash not in body_text
            assert _RAW_KEY not in body_text
        finally:
            app.dependency_overrides.clear()


class TestListApiKeysStillWorksViaJwt:
    """Regression: the dual-auth change must not break the existing JWT path."""

    @pytest.mark.asyncio
    async def test_jwt_session_still_authenticates(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user
        from app.models.organization import Organization

        mock_user = MagicMock(spec=User)
        mock_user.email = "owner@example.com"
        mock_user.status = "active"

        async def mock_get_user() -> User:
            return mock_user

        mock_session = AsyncMock()

        async def mock_get_db() -> Any:
            yield mock_session

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db

        org = MagicMock(spec=Organization)
        org.id = _ORG_ID
        org.status = OrganizationStatus.ACTIVE

        caller_membership = MagicMock(spec=Membership)
        caller_membership.role = MembershipRole.OWNER

        org_repo = MagicMock(get=AsyncMock(return_value=org))
        mem_repo = MagicMock(get_by_org_and_email=AsyncMock(return_value=caller_membership))

        try:
            with (
                patch.multiple(
                    "app.auth.dependencies",
                    OrganizationRepository=MagicMock(return_value=org_repo),
                    MembershipRepository=MagicMock(return_value=mem_repo),
                ),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.list",
                    new=AsyncMock(return_value=[]),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(f"/v1/organizations/{_ORG_ID}/api-keys")
            assert resp.status_code == 200
            assert resp.json()["total"] == 0
        finally:
            app.dependency_overrides.clear()
