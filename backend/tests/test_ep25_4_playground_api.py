"""Tests for the Playground API — EP-25.4 (AI Playground).

API-level wiring only: authentication/RBAC boundaries, connection lookup
(404 on cross-org/unknown), and that each endpoint calls
``PlaygroundService``/the repositories correctly. ``PlaygroundService``'s
own orchestration logic is covered by test_ep25_4_playground_service.py;
each adapter's ``complete()`` HTTP shape by
test_ep25_4_playground_adapters.py — this file focuses on what's unique to
the router layer.
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
from app.models.playground_execution import PlaygroundExecution, PlaygroundExecutionStatus
from app.models.provider_connection import ProviderConnection, ProviderType
from app.models.user import User

_ORG_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _connection(provider_type: ProviderType = ProviderType.OPENAI) -> ProviderConnection:
    conn = ProviderConnection()
    conn.id = uuid.uuid4()
    conn.organization_id = _ORG_ID
    conn.provider_type = provider_type
    conn.display_name = "My OpenAI"
    conn.is_active = True
    conn.encrypted_api_key = "v1:fake"
    conn.base_url = None
    conn.last_validation_status = None
    return conn


def _execution() -> PlaygroundExecution:
    execution = PlaygroundExecution()
    execution.id = uuid.uuid4()
    execution.organization_id = _ORG_ID
    execution.user_id = _USER_ID
    execution.provider_connection_id = uuid.uuid4()
    execution.project_id = None
    execution.provider = "openai"
    execution.model = "gpt-4o"
    execution.system_prompt = None
    execution.user_prompt = "Hi"
    execution.response_text = "Hello!"
    execution.temperature = None
    execution.top_p = None
    execution.max_tokens = None
    execution.prompt_tokens = 5
    execution.completion_tokens = 3
    execution.total_tokens = 8
    execution.estimated_cost = None
    execution.currency = "USD"
    execution.latency_ms = 120.5
    execution.status = PlaygroundExecutionStatus.SUCCEEDED
    execution.error_message = None
    execution.comparison_group_id = None
    execution.created_at = datetime.now(UTC)
    execution.updated_at = datetime.now(UTC)
    return execution


def _override_auth(app: Any, *, caller_role: MembershipRole) -> tuple[Any, Any]:
    """Mirrors tests/test_ep22_provider_connections.py's helper."""
    from app.api.deps import get_db
    from app.auth.dependencies import get_current_user

    mock_user = MagicMock(spec=User)
    mock_user.id = _USER_ID
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


class TestListPlaygroundConnections:
    @pytest.mark.asyncio
    async def test_unauthenticated_is_401(self, app: Any) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(f"/v1/organizations/{_ORG_ID}/playground/connections")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_can_list_connections(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                conn = _connection()
                with patch(
                    "app.api.v1.playground.ProviderConnectionRepository.list_by_org",
                    new=AsyncMock(
                        return_value=type("Page", (), {"items": [conn], "next_cursor": None})()
                    ),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(f"/v1/organizations/{_ORG_ID}/playground/connections")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["connections"]) == 1
            assert body["connections"][0]["provider_type"] == "openai"
            assert body["connections"][0]["has_credential"] is True
        finally:
            app.dependency_overrides.clear()


class TestExecutePlayground:
    @pytest.mark.asyncio
    async def test_viewer_can_execute(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                conn = _connection()
                execution = _execution()
                with (
                    patch(
                        "app.api.v1.playground.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=conn),
                    ),
                    patch(
                        "app.api.v1.playground.PlaygroundService.execute",
                        new=AsyncMock(return_value=execution),
                    ) as mock_execute,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/playground/execute",
                            json={
                                "provider_connection_id": str(conn.id),
                                "model_id": "gpt-4o",
                                "user_prompt": "Hi",
                            },
                        )
            assert resp.status_code == 201
            body = resp.json()
            assert body["response_text"] == "Hello!"
            assert body["status"] == "succeeded"
            mock_execute.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_unknown_connection_is_404(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                with patch(
                    "app.api.v1.playground.ProviderConnectionRepository.get",
                    new=AsyncMock(return_value=None),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/playground/execute",
                            json={
                                "provider_connection_id": str(uuid.uuid4()),
                                "model_id": "gpt-4o",
                                "user_prompt": "Hi",
                            },
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_connection_from_a_different_org_is_404(self, app: Any) -> None:
        """_get_connection() checks conn.organization_id == org_id — a
        connection that exists but belongs to a different org must never
        be usable via this org's Playground."""
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                foreign_conn = _connection()
                foreign_conn.organization_id = uuid.uuid4()
                with patch(
                    "app.api.v1.playground.ProviderConnectionRepository.get",
                    new=AsyncMock(return_value=foreign_conn),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/playground/execute",
                            json={
                                "provider_connection_id": str(foreign_conn.id),
                                "model_id": "gpt-4o",
                                "user_prompt": "Hi",
                            },
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestComparePlayground:
    @pytest.mark.asyncio
    async def test_missing_model_id_for_a_target_is_422(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                target_id = uuid.uuid4()
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as ac:
                    resp = await ac.post(
                        f"/v1/organizations/{_ORG_ID}/playground/compare",
                        json={
                            "targets": [str(target_id)],
                            "model_ids": {},
                            "user_prompt": "Hi",
                        },
                    )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_two_targets_share_one_comparison_group(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.MEMBER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                conn_a, conn_b = _connection(), _connection(ProviderType.ANTHROPIC)
                exec_a, exec_b = _execution(), _execution()

                async def fake_get(connection_id: uuid.UUID) -> ProviderConnection:
                    return conn_a if connection_id == conn_a.id else conn_b

                with (
                    patch(
                        "app.api.v1.playground.ProviderConnectionRepository.get",
                        new=AsyncMock(side_effect=fake_get),
                    ),
                    patch(
                        "app.api.v1.playground.PlaygroundService.execute",
                        new=AsyncMock(side_effect=[exec_a, exec_b]),
                    ) as mock_execute,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/playground/compare",
                            json={
                                "targets": [str(conn_a.id), str(conn_b.id)],
                                "model_ids": {str(conn_a.id): "gpt-4o", str(conn_b.id): "claude"},
                                "user_prompt": "Hi",
                            },
                        )
            assert resp.status_code == 201
            body = resp.json()
            assert len(body["executions"]) == 2
            assert mock_execute.await_count == 2
            # Every call shares the same comparison_group_id (sequential loop).
            group_ids = {
                call.kwargs["comparison_group_id"] for call in mock_execute.await_args_list
            }
            assert len(group_ids) == 1
            assert str(group_ids.pop()) == body["comparison_group_id"]
        finally:
            app.dependency_overrides.clear()


class TestPlaygroundHistory:
    @pytest.mark.asyncio
    async def test_list_history_returns_total_and_items(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                execution = _execution()
                with patch(
                    "app.api.v1.playground.PlaygroundExecutionRepository.list_for_org",
                    new=AsyncMock(return_value=([execution], 1)),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(f"/v1/organizations/{_ORG_ID}/playground/history")
            assert resp.status_code == 200
            body = resp.json()
            assert body["total"] == 1
            assert body["executions"][0]["user_prompt"] == "Hi"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_unknown_execution_is_404(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                with patch(
                    "app.api.v1.playground.PlaygroundExecutionRepository.get_for_org",
                    new=AsyncMock(return_value=None),
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.get(
                            f"/v1/organizations/{_ORG_ID}/playground/history/{uuid.uuid4()}"
                        )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_history_row(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                execution = _execution()
                with (
                    patch(
                        "app.api.v1.playground.PlaygroundExecutionRepository.get_for_org",
                        new=AsyncMock(return_value=execution),
                    ),
                    patch(
                        "app.api.v1.playground.PlaygroundExecutionRepository.soft_delete",
                        new=AsyncMock(),
                    ) as mock_delete,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.delete(
                            f"/v1/organizations/{_ORG_ID}/playground/history/{execution.id}"
                        )
            assert resp.status_code == 204
            mock_delete.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_rerun_calls_execute_with_original_params(self, app: Any) -> None:
        org_repo, mem_repo_lookup = _override_auth(app, caller_role=MembershipRole.VIEWER)
        try:
            with patch.multiple(
                "app.auth.dependencies",
                OrganizationRepository=MagicMock(return_value=org_repo),
                MembershipRepository=MagicMock(return_value=mem_repo_lookup),
            ):
                original = _execution()
                conn = _connection()
                original.provider_connection_id = conn.id
                new_execution = _execution()
                with (
                    patch(
                        "app.api.v1.playground.PlaygroundExecutionRepository.get_for_org",
                        new=AsyncMock(return_value=original),
                    ),
                    patch(
                        "app.api.v1.playground.ProviderConnectionRepository.get",
                        new=AsyncMock(return_value=conn),
                    ),
                    patch(
                        "app.api.v1.playground.PlaygroundService.execute",
                        new=AsyncMock(return_value=new_execution),
                    ) as mock_execute,
                ):
                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as ac:
                        resp = await ac.post(
                            f"/v1/organizations/{_ORG_ID}/playground/history/{original.id}/rerun"
                        )
            assert resp.status_code == 201
            mock_execute.assert_awaited_once()
            call_kwargs = mock_execute.await_args.kwargs
            assert call_kwargs["model_id"] == original.model
            assert call_kwargs["user_prompt"] == original.user_prompt
        finally:
            app.dependency_overrides.clear()
