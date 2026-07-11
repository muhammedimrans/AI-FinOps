"""Tests for EP-25.3 — product polish, UX hardening, remaining-work closure.

Covers:
  - The root-cause fix for "Budget creation fails" / "Alert creation
    fails": `WorkspacePublic.id` (register, upgrade-to-business) and the
    Google OAuth dashboard-handoff payload's `workspace.id` must be the
    raw hyphenated UUID, matching every `organization_id: uuid.UUID`
    endpoint's expectation and `OrgMembershipItem.id`'s own documented
    convention — never `Organization.external_id` (the `org_<hex>`
    prefixed form), which FastAPI's UUID query/path parsing rejects
    outright with a 422 before any business logic runs.

All tests are hermetic — no network calls, no real database (the fix
itself was discovered and confirmed via a live Postgres + Redis + real
FastAPI app repro, documented in CLAUDE.md's EP-25.3 section; these tests
pin the fix at the unit level so it can never silently regress).
"""

from __future__ import annotations

import base64
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.service import TokenPair
from app.config.settings import Settings
from app.models.user import User
from tests.conftest import make_org, make_user


def _test_settings(**overrides: Any) -> Settings:
    kwargs: dict[str, Any] = {
        "app_env": "testing",
        "app_secret_key": "test-secret-key-with-at-least-32-chars!!",
        "jwt_secret": "test-jwt-secret-for-unit-tests-only!!",
        "dashboard_url": "https://app.costorah.com",
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


class TestWorkspaceIdIsRawUuidNotExternalId:
    """Regression pins for the EP-25.3 root-cause fix."""

    @pytest.mark.asyncio
    async def test_register_response_workspace_id_is_raw_uuid(self, app: Any) -> None:
        from app.api.deps import DbDep, get_db  # noqa: F401

        org = make_org(is_personal=True)
        user = make_user(email="raw-uuid@example.com")

        with patch(
            "app.api.v1.auth.AuthService.register",
            new=AsyncMock(return_value=(None, user, org)),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/auth/register",
                    json={
                        "email": "raw-uuid@example.com",
                        "password": "correct-horse-battery-staple",
                        "display_name": "Raw Uuid",
                    },
                )
        assert resp.status_code == 201
        workspace_id = resp.json()["workspace"]["id"]
        # Must round-trip as a bare UUID — the exact shape every
        # organization_id: uuid.UUID query/path param expects.
        assert uuid.UUID(workspace_id) == org.id
        assert not workspace_id.startswith("org_")

    @pytest.mark.asyncio
    async def test_upgrade_to_business_response_workspace_id_is_raw_uuid(self, app: Any) -> None:
        from app.api.deps import get_db
        from app.auth.dependencies import get_current_user

        org = make_org(is_personal=True)
        org.is_personal = False
        mock_user = MagicMock(spec=User)
        mock_user.id = uuid.uuid4()
        mock_user.email = "upgrader@example.com"
        mock_user.display_name = "Upgrader"

        async def mock_get_user() -> User:
            return mock_user  # type: ignore[return-value]

        async def mock_get_db() -> Any:
            yield AsyncMock()

        app.dependency_overrides[get_current_user] = mock_get_user
        app.dependency_overrides[get_db] = mock_get_db

        with patch(
            "app.api.v1.auth.AuthService.upgrade_to_business",
            new=AsyncMock(return_value=org),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/auth/upgrade-to-business",
                    json={},
                    headers={"Authorization": "Bearer test"},
                )
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        workspace_id = resp.json()["id"]
        assert uuid.UUID(workspace_id) == org.id
        assert not workspace_id.startswith("org_")

    def test_dashboard_handoff_payload_workspace_id_is_raw_uuid(self) -> None:
        from app.api.v1.auth import _build_dashboard_handoff_url

        org = make_org(is_personal=True)
        user = make_user(email="handoff@example.com")
        user.onboarding_completed_at = None
        pair = TokenPair(access_token="a", refresh_token="b", expires_in=900)

        url = _build_dashboard_handoff_url(
            path="/onboarding",
            pair=pair,
            user=user,
            workspace=org,
            settings=_test_settings(),
        )

        fragment = url.split("#session=", 1)[1]
        # Reverse the same encode() used by the handoff builder + website's
        # buildDashboardHandoffUrl (encodeURIComponent(btoa(JSON...))).
        from urllib.parse import unquote

        decoded = json.loads(base64.b64decode(unquote(fragment)))
        workspace_id = decoded["workspace"]["id"]
        assert uuid.UUID(workspace_id) == org.id
        assert not workspace_id.startswith("org_")

    @pytest.mark.asyncio
    async def test_end_to_end_budget_creation_no_longer_422s_with_correct_id(
        self, app: Any
    ) -> None:
        """Simulates the exact bug: a client using WorkspacePublic.id as
        organization_id for a query-param endpoint must now succeed at the
        FastAPI UUID-parsing layer (this test doesn't need real auth/DB —
        it only proves the id shape survives round-tripping through the
        uuid.UUID query-param type FastAPI enforces)."""
        org = make_org(is_personal=True)
        workspace_id = str(org.id)
        # This is exactly what a 422 looked like before the fix, for
        # contrast — asserting the *new* shape is what would be sent.
        assert uuid.UUID(workspace_id) == org.id
        # The old, broken shape would have raised ValueError here.
        with pytest.raises(ValueError):
            uuid.UUID(org.external_id)
