"""Tests for organization API key management (EP-14 Phase 1).

Covers:
  - OrganizationApiKeyRepository: list / get_by_hash / delete / update_last_used
  - OrganizationApiKeyService: generation, hashing, validation, expiration
  - GET/POST/DELETE /v1/organizations/{org_id}/api-keys
  - Permission tests (API_KEY_READ / API_KEY_WRITE by role)
  - Security tests (raw key never persisted or re-returned, hash uniqueness)

All tests are hermetic — no network calls, no real database.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.membership import Membership, MembershipRole
from app.models.organization_api_key import OrganizationApiKey
from app.models.user import User
from app.services.organization_api_key_service import (
    InvalidExpirationError,
    InvalidPermissionError,
    OrganizationApiKeyService,
)
from tests.conftest import make_api_key

_ORG_ID = uuid.uuid4()


# ══════════════════════════════════════════════════════════════════════════════
# Repository tests
# ══════════════════════════════════════════════════════════════════════════════


class TestList:
    @pytest.mark.asyncio
    async def test_returns_keys_for_org(self) -> None:
        from app.repositories.organization_api_key_repository import (
            OrganizationApiKeyRepository,
        )

        key = make_api_key(org_id=_ORG_ID)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [key]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = OrganizationApiKeyRepository(mock_session)
        result = await repo.list(_ORG_ID)
        assert result == [key]

    @pytest.mark.asyncio
    async def test_empty_org_returns_empty_list(self) -> None:
        from app.repositories.organization_api_key_repository import (
            OrganizationApiKeyRepository,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = OrganizationApiKeyRepository(mock_session)
        result = await repo.list(_ORG_ID)
        assert result == []


class TestGetByHash:
    @pytest.mark.asyncio
    async def test_returns_matching_key(self) -> None:
        from app.repositories.organization_api_key_repository import (
            OrganizationApiKeyRepository,
        )

        key = make_api_key(key_hash="deadbeef" * 8)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = key
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = OrganizationApiKeyRepository(mock_session)
        result = await repo.get_by_hash("deadbeef" * 8)
        assert result is key

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_hash(self) -> None:
        from app.repositories.organization_api_key_repository import (
            OrganizationApiKeyRepository,
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = OrganizationApiKeyRepository(mock_session)
        result = await repo.get_by_hash("0" * 64)
        assert result is None


class TestDelete:
    @pytest.mark.asyncio
    async def test_soft_deletes(self) -> None:
        from app.repositories.organization_api_key_repository import (
            OrganizationApiKeyRepository,
        )

        key = make_api_key()
        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()

        repo = OrganizationApiKeyRepository(mock_session)
        actor = uuid.uuid4()
        result = await repo.delete(key, deleted_by=actor)
        assert result.deleted_at is not None
        assert result.deleted_by == actor


class TestUpdateLastUsed:
    @pytest.mark.asyncio
    async def test_stamps_last_used_at(self) -> None:
        from app.repositories.organization_api_key_repository import (
            OrganizationApiKeyRepository,
        )

        key = make_api_key()
        assert key.last_used_at is None
        mock_session = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        repo = OrganizationApiKeyRepository(mock_session)
        result = await repo.update_last_used(key)
        assert result.last_used_at is not None


# ══════════════════════════════════════════════════════════════════════════════
# Service tests
# ══════════════════════════════════════════════════════════════════════════════


class TestValidatePermissions:
    def test_accepts_known_permissions(self) -> None:
        result = OrganizationApiKeyService.validate_permissions(["usage:read", "org:read"])
        assert result == ["usage:read", "org:read"]

    def test_accepts_empty_list(self) -> None:
        assert OrganizationApiKeyService.validate_permissions([]) == []

    def test_rejects_unknown_scope(self) -> None:
        with pytest.raises(InvalidPermissionError):
            OrganizationApiKeyService.validate_permissions(["not:a:real:scope"])


class TestResolveExpiration:
    def test_never_returns_none(self) -> None:
        assert OrganizationApiKeyService.resolve_expiration("never") is None

    def test_30d_returns_future_datetime(self) -> None:
        result = OrganizationApiKeyService.resolve_expiration("30d")
        assert result is not None
        delta = result - datetime.now(UTC)
        assert timedelta(days=29) < delta <= timedelta(days=30)

    def test_90d_returns_future_datetime(self) -> None:
        result = OrganizationApiKeyService.resolve_expiration("90d")
        assert result is not None
        delta = result - datetime.now(UTC)
        assert timedelta(days=89) < delta <= timedelta(days=90)

    def test_unknown_option_raises(self) -> None:
        with pytest.raises(InvalidExpirationError):
            OrganizationApiKeyService.resolve_expiration("1y")


class TestIsExpired:
    def test_no_expiry_is_never_expired(self) -> None:
        key = make_api_key()
        key.expires_at = None
        assert OrganizationApiKeyService.is_expired(key) is False

    def test_future_expiry_is_not_expired(self) -> None:
        key = make_api_key()
        key.expires_at = datetime.now(UTC) + timedelta(days=1)
        assert OrganizationApiKeyService.is_expired(key) is False

    def test_past_expiry_is_expired(self) -> None:
        key = make_api_key()
        key.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert OrganizationApiKeyService.is_expired(key) is True


class TestCreateKey:
    @pytest.mark.asyncio
    async def test_generates_key_with_correct_prefix(self) -> None:
        mock_session = AsyncMock()
        service = OrganizationApiKeyService(mock_session)
        with patch.object(service._repo, "create", new=AsyncMock(side_effect=lambda r: r)):
            record, raw_key = await service.create_key(
                organization_id=_ORG_ID,
                name="CI key",
                description=None,
                permissions=["usage:read"],
                expiration="never",
                created_by=uuid.uuid4(),
            )
        assert raw_key.startswith("costorah_live_")
        assert record.key_prefix.startswith("costorah_live_")
        # The stored prefix must be a strict, shorter truncation of the raw key.
        assert len(record.key_prefix) < len(raw_key)
        assert raw_key.startswith(record.key_prefix)

    @pytest.mark.asyncio
    async def test_never_persists_raw_key(self) -> None:
        mock_session = AsyncMock()
        service = OrganizationApiKeyService(mock_session)
        with patch.object(service._repo, "create", new=AsyncMock(side_effect=lambda r: r)):
            record, raw_key = await service.create_key(
                organization_id=_ORG_ID,
                name="CI key",
                description=None,
                permissions=[],
                expiration="never",
                created_by=uuid.uuid4(),
            )
        assert record.key_hash == hashlib.sha256(raw_key.encode()).hexdigest()
        # The full raw secret must never appear verbatim anywhere on the record.
        assert raw_key not in vars(record).values()

    @pytest.mark.asyncio
    async def test_two_keys_never_collide(self) -> None:
        mock_session = AsyncMock()
        service = OrganizationApiKeyService(mock_session)
        with patch.object(service._repo, "create", new=AsyncMock(side_effect=lambda r: r)):
            _, raw_a = await service.create_key(
                organization_id=_ORG_ID,
                name="a",
                description=None,
                permissions=[],
                expiration="never",
                created_by=uuid.uuid4(),
            )
            _, raw_b = await service.create_key(
                organization_id=_ORG_ID,
                name="b",
                description=None,
                permissions=[],
                expiration="never",
                created_by=uuid.uuid4(),
            )
        assert raw_a != raw_b

    @pytest.mark.asyncio
    async def test_rejects_invalid_permission_before_persisting(self) -> None:
        mock_session = AsyncMock()
        service = OrganizationApiKeyService(mock_session)
        with patch.object(service._repo, "create", new=AsyncMock()) as create:
            with pytest.raises(InvalidPermissionError):
                await service.create_key(
                    organization_id=_ORG_ID,
                    name="bad",
                    description=None,
                    permissions=["not:real"],
                    expiration="never",
                    created_by=uuid.uuid4(),
                )
            create.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sets_expires_at_for_30d(self) -> None:
        mock_session = AsyncMock()
        service = OrganizationApiKeyService(mock_session)
        with patch.object(service._repo, "create", new=AsyncMock(side_effect=lambda r: r)):
            record, _ = await service.create_key(
                organization_id=_ORG_ID,
                name="expiring",
                description=None,
                permissions=[],
                expiration="30d",
                created_by=uuid.uuid4(),
            )
        assert record.expires_at is not None


class TestValidateKey:
    @pytest.mark.asyncio
    async def test_returns_matching_active_key(self) -> None:
        mock_session = AsyncMock()
        service = OrganizationApiKeyService(mock_session)
        raw = "costorah_live_abc123"
        stored = make_api_key(key_hash=hashlib.sha256(raw.encode()).hexdigest())
        with patch.object(service._repo, "get_by_hash", new=AsyncMock(return_value=stored)):
            result = await service.validate_key(raw)
        assert result is stored

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_key(self) -> None:
        mock_session = AsyncMock()
        service = OrganizationApiKeyService(mock_session)
        with patch.object(service._repo, "get_by_hash", new=AsyncMock(return_value=None)):
            result = await service.validate_key("costorah_live_nope")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_expired_key(self) -> None:
        mock_session = AsyncMock()
        service = OrganizationApiKeyService(mock_session)
        stored = make_api_key()
        stored.expires_at = datetime.now(UTC) - timedelta(days=1)
        with patch.object(service._repo, "get_by_hash", new=AsyncMock(return_value=stored)):
            result = await service.validate_key("costorah_live_expired")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# API tests
# ══════════════════════════════════════════════════════════════════════════════


def _stamp_and_return(record: OrganizationApiKey) -> OrganizationApiKey:
    """Fake repo.create(): stamp server-default fields a real flush would set."""
    record.created_at = datetime.now(UTC)
    record.updated_at = record.created_at
    return record


def _active_org() -> Any:
    from app.models.organization import Organization, OrganizationStatus

    org = MagicMock(spec=Organization)
    org.id = _ORG_ID
    org.status = OrganizationStatus.ACTIVE
    return org


def _override_auth(
    app: Any, *, caller_role: MembershipRole, caller_email: str = "caller@example.com"
) -> Any:
    """Override auth so the caller is a member of _ORG_ID with the given role."""
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.id = uuid.uuid4()
    mock_user.email = caller_email
    mock_user.status = "active"

    async def mock_get_user() -> User:
        return mock_user  # type: ignore[return-value]

    mock_session = AsyncMock()

    async def mock_get_db() -> Any:
        yield mock_session

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db

    caller_membership = MagicMock(spec=Membership)
    caller_membership.role = caller_role

    org_repo = MagicMock()
    org_repo.get = AsyncMock(return_value=_active_org())
    mem_repo_for_org_lookup = MagicMock()
    mem_repo_for_org_lookup.get_by_org_and_email = AsyncMock(return_value=caller_membership)

    return mock_session, org_repo, mem_repo_for_org_lookup


def _auth_patches(org_repo: Any, mem_repo_lookup: Any) -> Any:
    return patch.multiple(
        "app.auth.dependencies",
        OrganizationRepository=MagicMock(return_value=org_repo),
        MembershipRepository=MagicMock(return_value=mem_repo_lookup),
    )


class TestListApiKeysEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/v1/organizations/{_ORG_ID}/api-keys")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_member_is_403(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        mock_user = MagicMock(spec=User)
        mock_user.email = "outsider@example.com"
        mock_user.status = "active"

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db
        try:
            org_repo = MagicMock(get=AsyncMock(return_value=_active_org()))
            mem_repo = MagicMock(get_by_org_and_email=AsyncMock(return_value=None))
            with _auth_patches(org_repo, mem_repo):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(f"/v1/organizations/{_ORG_ID}/api-keys")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_viewer_can_list(self, app: Any) -> None:
        """API_KEY_READ is granted to every role, including VIEWER."""
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            key = make_api_key(org_id=_ORG_ID, name="Prod ingestion")
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.list",
                    new=AsyncMock(return_value=[key]),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.get(f"/v1/organizations/{_ORG_ID}/api-keys")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            assert body["keys"][0]["name"] == "Prod ingestion"
            assert body["keys"][0]["prefix"] == key.key_prefix
            # Never returned under any key name.
            assert "key_hash" not in body["keys"][0]
            assert "api_key" not in body["keys"][0]
        finally:
            app.dependency_overrides.clear()


class TestCreateApiKeyEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"/v1/organizations/{_ORG_ID}/api-keys", json={"name": "x"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with _auth_patches(org_repo, mem_repo_lookup):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/api-keys", json={"name": "x"}
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_create(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with _auth_patches(org_repo, mem_repo_lookup):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/api-keys", json={"name": "x"}
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_admin_can_create_and_receives_raw_key_once(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.create",
                    new=AsyncMock(side_effect=_stamp_and_return),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        json={
                            "name": "Prod ingestion",
                            "description": "used by the nightly job",
                            "permissions": ["usage:read"],
                            "expiration": "30d",
                        },
                    )
            assert resp.status_code == 201
            body = resp.json()
            assert body["api_key"].startswith("costorah_live_")
            assert body["prefix"].startswith("costorah_live_")
            assert body["api_key"].startswith(body["prefix"])
            assert body["name"] == "Prod ingestion"
            assert body["permissions"] == ["usage:read"]
            assert body["expires_at"] is not None
            assert "key_hash" not in body
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_owner_can_create(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.create",
                    new=AsyncMock(side_effect=_stamp_and_return),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        json={"name": "Owner key"},
                    )
            assert resp.status_code == 201
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_permission_scope_is_422(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with _auth_patches(org_repo, mem_repo_lookup):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        json={"name": "bad", "permissions": ["not:a:scope"]},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_expiration_is_422(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with _auth_patches(org_repo, mem_repo_lookup):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/api-keys",
                        json={"name": "bad", "expiration": "1y"},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_missing_name_is_422(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.OWNER)
        try:
            with _auth_patches(org_repo, mem_repo_lookup):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(f"/v1/organizations/{_ORG_ID}/api-keys", json={})
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()


class TestDeleteApiKeyEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.delete(f"/v1/organizations/{_ORG_ID}/api-keys/{uuid.uuid4()}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with _auth_patches(org_repo, mem_repo_lookup):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/organizations/{_ORG_ID}/api-keys/{uuid.uuid4()}")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_missing_key_is_404(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.get",
                    new=AsyncMock(return_value=None),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/organizations/{_ORG_ID}/api-keys/{uuid.uuid4()}")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_key_from_another_org_is_404(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        other_org_key = make_api_key(org_id=uuid.uuid4())
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.get",
                    new=AsyncMock(return_value=other_org_key),
                ),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(
                        f"/v1/organizations/{_ORG_ID}/api-keys/{other_org_key.id}"
                    )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_admin_can_revoke(self, app: Any) -> None:
        _session, org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        target = make_api_key(org_id=_ORG_ID)
        try:
            with (
                _auth_patches(org_repo, mem_repo_lookup),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.get",
                    new=AsyncMock(return_value=target),
                ),
                patch(
                    "app.repositories.organization_api_key_repository."
                    "OrganizationApiKeyRepository.soft_delete",
                    new=AsyncMock(side_effect=lambda r, deleted_by=None: r),
                ) as soft_delete,
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(f"/v1/organizations/{_ORG_ID}/api-keys/{target.id}")
            assert resp.status_code == 204
            soft_delete.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()
