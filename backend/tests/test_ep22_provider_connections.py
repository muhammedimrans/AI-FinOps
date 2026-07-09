"""Tests for Provider Connections CRUD + credential API (EP-22).

Covers:
  - GET/POST/PATCH/DELETE /v1/organizations/{org_id}/provider-connections[...]
  - POST .../provider-connections/{id}/test
  - POST .../provider-connections/{id}/rotate
  - PROVIDER_READ (every role) / PROVIDER_WRITE / PROVIDER_DELETE
    (ADMIN+OWNER only — MEMBER has PROVIDER_READ but not WRITE/DELETE,
    per app.auth.rbac._MEMBER_PERMS vs _ADMIN_PERMS) authorization
  - A decrypted API key is never present anywhere in a response body —
    only ``masked_api_key`` (EP-22 Part 7 security requirement)

All tests are hermetic — no network calls, no real database. Provider
validation is exercised by patching ``ProviderValidator.validate`` directly
(unit-level fake — the live HTTP validation path itself is covered by
``test_ep22_provider_validator.py`` with mocked httpx transports), so these
tests focus on the API/service wiring: encryption round-trip, masking,
persistence of health fields, and authorization.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.provider_connection import (
    ProviderConnection,
    ProviderHealthStatus,
    ProviderType,
    ProviderValidationStatus,
)
from app.models.user import User
from app.providers.validation import ValidationResult
from app.security.encryption import EncryptionService
from tests.conftest import make_provider_connection

_ORG_ID = uuid.uuid4()

_TEST_ENCRYPTION = EncryptionService(primary_secret="test-secret-key-for-testing-only-32ch")


def _timestamped(conn: ProviderConnection) -> ProviderConnection:
    """make_provider_connection() returns a transient instance with no
    created_at/updated_at (only populated on a real flush/refresh) — set
    them explicitly so ProviderConnectionResponse serialization succeeds,
    matching tests/test_member_management.py's identical need."""
    conn.created_at = datetime.now(UTC)
    conn.updated_at = datetime.now(UTC)
    return conn


def _override_auth(app: Any, *, caller_role: MembershipRole) -> tuple[Any, Any]:
    """Mirrors tests/test_member_management.py's _override_auth helper."""
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.email = "caller@example.com"
    mock_user.status = "active"

    async def mock_get_user() -> User:
        return mock_user

    async def mock_get_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_current_user] = mock_get_user
    app.dependency_overrides[get_db] = mock_get_db

    org = MagicMock(spec=Organization)
    org.id = _ORG_ID
    org.status = OrganizationStatus.ACTIVE

    caller_membership = MagicMock(spec=Membership)
    caller_membership.role = caller_role

    org_repo = MagicMock()
    org_repo.get = AsyncMock(return_value=org)
    mem_repo_for_org_lookup = MagicMock()
    mem_repo_for_org_lookup.get_by_org_and_email = AsyncMock(return_value=caller_membership)

    return org_repo, mem_repo_for_org_lookup


class TestListProviderConnectionsEndpoint:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/v1/organizations/{_ORG_ID}/provider-connections")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_can_list(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                conn = _timestamped(
                    make_provider_connection(
                        org_id=_ORG_ID,
                        display_name="OpenAI prod",
                        encrypted_api_key=_TEST_ENCRYPTION.encrypt("sk-" + "a" * 40),
                    )
                )
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.list_by_org",
                        new=AsyncMock(
                            return_value=type("Page", (), {"items": [conn], "next_cursor": None})()
                        ),
                    ),
                    patch(
                        "app.api.v1.provider_connections._credentials._encryption",
                        _TEST_ENCRYPTION,
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(f"/v1/organizations/{_ORG_ID}/provider-connections")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            item = body["connections"][0]
            assert item["display_name"] == "OpenAI prod"
            assert item["health_status"] == "unknown"
            assert item["has_credential"] is True
            assert item["masked_api_key"] is not None
            assert item["masked_api_key"].startswith("sk-")
            assert "a" * 40 not in resp.text  # raw key never leaves the process
        finally:
            app.dependency_overrides.clear()


class TestCreateProviderConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_create_without_key(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                created = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, display_name="My OpenAI")
                )
                with patch(
                    "app.api.v1.provider_connections.ProviderConnectionRepository.create",
                    new=AsyncMock(return_value=created),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections",
                            json={"provider_type": "openai", "display_name": "My OpenAI"},
                        )
            assert resp.status_code == 201
            body = resp.json()
            assert body["display_name"] == "My OpenAI"
            assert body["is_active"] is True
            assert body["has_credential"] is False
            assert body["masked_api_key"] is None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_with_key_validates_immediately(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                created = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, display_name="My OpenAI")
                )
                healthy = ValidationResult(
                    validation_status=ProviderValidationStatus.HEALTHY,
                    health_status=ProviderHealthStatus.HEALTHY,
                    detail="Connection healthy.",
                )
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.create",
                        new=AsyncMock(return_value=created),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=AsyncMock(return_value=created),
                    ),
                    patch(
                        "app.providers.validation.ProviderValidator.validate",
                        new=AsyncMock(return_value=healthy),
                    ) as validate_mock,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections",
                            json={
                                "provider_type": "openai",
                                "display_name": "My OpenAI",
                                "api_key": "sk-" + "a" * 40,
                            },
                        )
            assert resp.status_code == 201
            validate_mock.assert_awaited_once()
            # The plaintext key must never appear in the response body.
            assert "sk-" + "a" * 40 not in resp.text
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_invalid_provider_type_is_422(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/provider-connections",
                        json={"provider_type": "not-a-provider", "display_name": "X"},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_create(self, app: Any) -> None:
        """MEMBER has PROVIDER_READ but not PROVIDER_WRITE — only ADMIN/OWNER can."""
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/provider-connections",
                        json={"provider_type": "openai", "display_name": "Nope"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestUpdateProviderConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_update_display_name_and_active(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, display_name="Old")
                )
                updated = _timestamped(make_provider_connection(org_id=_ORG_ID, display_name="New"))
                updated.id = existing.id
                updated.is_active = False
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=AsyncMock(return_value=updated),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}",
                            json={"display_name": "New", "is_active": False},
                        )
            assert resp.status_code == 200
            assert resp.json()["display_name"] == "New"
            assert resp.json()["is_active"] is False
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_not_found_is_404(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                with patch(
                    "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                    new=AsyncMock(return_value=None),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{uuid.uuid4()}",
                            json={"display_name": "X"},
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_does_not_accept_api_key_field(self, app: Any) -> None:
        """api_key is intentionally not part of UpdateProviderConnectionRequest —
        rotation is a distinct, separately-audited endpoint."""
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(make_provider_connection(org_id=_ORG_ID))
                captured: dict[str, Any] = {}

                async def fake_update(self: Any, conn: Any, **kwargs: Any) -> Any:
                    captured.update(kwargs)
                    return existing

                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=fake_update,
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.patch(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}",
                            json={"display_name": "New", "api_key": "sk-should-be-ignored"},
                        )
            assert resp.status_code == 200
            assert "api_key" not in captured
            assert "encrypted_api_key" not in captured
        finally:
            app.dependency_overrides.clear()


class TestDeleteProviderConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_delete(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(make_provider_connection(org_id=_ORG_ID))
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.soft_delete",
                        new=AsyncMock(return_value=existing),
                    ) as soft_delete,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.delete(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}"
                        )
            assert resp.status_code == 204
            soft_delete.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_delete(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.delete(
                        f"/v1/organizations/{_ORG_ID}/provider-connections/{uuid.uuid4()}"
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestTestProviderConnectionEndpoint:
    @pytest.mark.asyncio
    async def test_successful_test_marks_healthy(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(
                        org_id=_ORG_ID,
                        provider_type=ProviderType.OPENAI,
                        encrypted_api_key=_TEST_ENCRYPTION.encrypt("sk-" + "a" * 40),
                    )
                )
                healthy = ValidationResult(
                    validation_status=ProviderValidationStatus.HEALTHY,
                    health_status=ProviderHealthStatus.HEALTHY,
                    detail="Connection healthy.",
                )
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections._credentials._encryption",
                        _TEST_ENCRYPTION,
                    ),
                    patch(
                        "app.providers.validation.ProviderValidator.validate",
                        new=AsyncMock(return_value=healthy),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}/test"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["tested"] is True
            assert body["health_status"] == "healthy"
            assert body["last_validation_status"] == "healthy"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_failed_test_marks_critical(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(
                        org_id=_ORG_ID,
                        provider_type=ProviderType.OPENAI,
                        encrypted_api_key=_TEST_ENCRYPTION.encrypt("sk-bad"),
                    )
                )
                invalid = ValidationResult(
                    validation_status=ProviderValidationStatus.INVALID_API_KEY,
                    health_status=ProviderHealthStatus.CRITICAL,
                    detail="The API key is invalid or has been revoked.",
                )
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections._credentials._encryption",
                        _TEST_ENCRYPTION,
                    ),
                    patch(
                        "app.providers.validation.ProviderValidator.validate",
                        new=AsyncMock(return_value=invalid),
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}/test"
                        )
            assert resp.status_code == 200
            body = resp.json()
            assert body["tested"] is True
            assert body["health_status"] == "critical"
            assert body["last_validation_status"] == "invalid_api_key"
            assert "revoked" in body["detail"]
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_no_credential_configured_still_returns_tested_result(self, app: Any) -> None:
        """A connection with no stored key still gets a real, honest result —
        the validator surfaces "no credential" as an authentication failure
        rather than a fabricated success (Ollama, which needs no key, is the
        one exception — covered by test_ep22_provider_validator.py)."""
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(org_id=_ORG_ID, provider_type=ProviderType.OPENAI)
                )
                assert existing.encrypted_api_key is None
                no_key = ValidationResult(
                    validation_status=ProviderValidationStatus.INVALID_API_KEY,
                    health_status=ProviderHealthStatus.CRITICAL,
                    detail="The API key is invalid or has been revoked.",
                )
                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.providers.validation.ProviderValidator.validate",
                        new=AsyncMock(return_value=no_key),
                    ) as validate_mock,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}/test"
                        )
            assert resp.status_code == 200
            # api_key=None was passed through — the endpoint never invents a key.
            validate_mock.assert_awaited_once_with(ProviderType.OPENAI, api_key=None, base_url=None)
        finally:
            app.dependency_overrides.clear()


class TestRotateProviderConnectionKeyEndpoint:
    @pytest.mark.asyncio
    async def test_admin_can_rotate_key(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                existing = _timestamped(
                    make_provider_connection(
                        org_id=_ORG_ID,
                        provider_type=ProviderType.OPENAI,
                        encrypted_api_key=_TEST_ENCRYPTION.encrypt("sk-" + "old" * 12),
                    )
                )
                healthy = ValidationResult(
                    validation_status=ProviderValidationStatus.HEALTHY,
                    health_status=ProviderHealthStatus.HEALTHY,
                    detail="Connection healthy.",
                )
                captured: dict[str, Any] = {}

                async def fake_update(self: Any, conn: Any, **kwargs: Any) -> Any:
                    captured.update(kwargs)
                    existing.encrypted_api_key = kwargs.get(
                        "encrypted_api_key", existing.encrypted_api_key
                    )
                    return existing

                with (
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=existing),
                    ),
                    patch(
                        "app.api.v1.provider_connections.ProviderConnectionRepository.update",
                        new=fake_update,
                    ),
                    patch(
                        "app.api.v1.provider_connections._credentials._encryption",
                        _TEST_ENCRYPTION,
                    ),
                    patch(
                        "app.providers.validation.ProviderValidator.validate",
                        new=AsyncMock(return_value=healthy),
                    ) as validate_mock,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/provider-connections/{existing.id}/rotate",
                            json={"api_key": "sk-" + "newnew" * 8},
                        )
            assert resp.status_code == 200
            # The new plaintext key was used for validation...
            validate_mock.assert_awaited_once_with(
                ProviderType.OPENAI, api_key="sk-" + "newnew" * 8, base_url=None
            )
            # ...but never appears anywhere in the response.
            assert "newnew" not in resp.text
            # The stored ciphertext changed (encrypted_api_key was re-set).
            assert captured["encrypted_api_key"] != _TEST_ENCRYPTION.encrypt("sk-" + "old" * 12)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_member_cannot_rotate(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/provider-connections/{uuid.uuid4()}/rotate",
                        json={"api_key": "sk-anything"},
                    )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_empty_key_is_422(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.ADMIN)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/provider-connections/{uuid.uuid4()}/rotate",
                        json={"api_key": ""},
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()
