"""EP-26.0.3.1 — repository-wide UUID vs external_id consistency fix.

Root cause: `ProjectResponse.id` and `ProviderConnectionResponse.id` both
returned `<model>.external_id` (a type-prefixed hex string, e.g.
`"conn_0123456789abcdef0123456789abcdef"`), while every mutating endpoint
on both resources (`PATCH`/`DELETE .../{project_id}`,
`PATCH`/`DELETE`/`test`/`rotate`/`sync-status`/`sync` under
`.../{connection_id}`) type-validates its path parameter as `uuid.UUID`.
`uuid.UUID("conn_<hex>")` always raises — the "conn_"/"proj_" prefix isn't
valid hex — so every dashboard action that reuses the API's own response
`id` (rename, activate/deactivate, Test Connection, Rotate Key, Sync Now,
Delete — confirmed via direct read of Connections.tsx/Projects.tsx, both
of which pass `connection.id`/`project.id` straight into these calls)
would 422 in real use. No existing test caught this because every prior
test constructs its fixtures with a known raw UUID and calls endpoints
with that UUID directly — none round-trip through a real
create-response-id -> reuse-in-a-later-request flow the way a real
browser session does.

Fix: `id` is now the raw UUID on both response schemas, matching the
already-correct convention `BudgetResponse`/`AlertResponse`/
`ApiKeyResponse`/`InvitationResponse` all use.
"""

from __future__ import annotations

import uuid

import pytest

from app.api.v1.projects import _to_response as project_to_response
from app.api.v1.provider_connections import _to_response as connection_to_response
from tests.conftest import make_project, make_provider_connection


def _timestamp(obj):
    from datetime import UTC, datetime

    obj.created_at = datetime.now(UTC)
    obj.updated_at = datetime.now(UTC)
    return obj


class TestProjectIdIsRawUuid:
    def test_response_id_matches_model_id_exactly(self) -> None:
        project = _timestamp(make_project())
        response = project_to_response(project)
        assert response.id == project.id

    def test_response_id_is_never_the_external_id(self) -> None:
        project = _timestamp(make_project())
        response = project_to_response(project)
        assert str(response.id) != project.external_id
        assert not str(response.id).startswith("proj_")

    def test_response_id_round_trips_through_uuid_uuid(self) -> None:
        """The exact failure mode this EP fixes: passing the response's own
        `id` straight into `uuid.UUID(...)` — precisely what FastAPI does
        when parsing a `{project_id}: uuid.UUID` path parameter — must
        succeed, not raise."""
        project = _timestamp(make_project())
        response = project_to_response(project)
        parsed = uuid.UUID(str(response.id))
        assert parsed == project.id


class TestProviderConnectionIdIsRawUuid:
    def test_response_id_matches_model_id_exactly(self) -> None:
        conn = _timestamp(make_provider_connection())
        response = connection_to_response(conn)
        assert response.id == conn.id

    def test_response_id_is_never_the_external_id(self) -> None:
        conn = _timestamp(make_provider_connection())
        response = connection_to_response(conn)
        assert str(response.id) != conn.external_id
        assert not str(response.id).startswith("conn_")

    def test_response_id_round_trips_through_uuid_uuid(self) -> None:
        conn = _timestamp(make_provider_connection())
        response = connection_to_response(conn)
        parsed = uuid.UUID(str(response.id))
        assert parsed == conn.id


class TestExternalIdPrefixIsNotAValidUuid:
    """Pins the root-cause mechanism itself, independent of any endpoint —
    documents *why* the bug was real, not just that the fix exists."""

    def test_uuid_parsing_rejects_the_conn_prefix(self) -> None:
        with pytest.raises(ValueError):
            uuid.UUID("conn_0123456789abcdef0123456789abcdef")

    def test_uuid_parsing_rejects_the_proj_prefix(self) -> None:
        with pytest.raises(ValueError):
            uuid.UUID("proj_0123456789abcdef0123456789abcdef")
