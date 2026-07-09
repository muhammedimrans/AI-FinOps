"""Provider Connections API — EP-22.

Endpoints:
  GET    /v1/organizations/{org_id}/provider-connections               — list
  POST   /v1/organizations/{org_id}/provider-connections               — create
  PATCH  /v1/organizations/{org_id}/provider-connections/{conn_id}     — update
  DELETE /v1/organizations/{org_id}/provider-connections/{conn_id}     — soft-delete
  POST   /v1/organizations/{org_id}/provider-connections/{conn_id}/test — test connectivity

Authorization: PROVIDER_READ / PROVIDER_WRITE / PROVIDER_DELETE — all
already defined in app.auth.rbac (EP-13), no changes needed.

The ProviderConnection model and ProviderConnectionRepository already
existed (app.models.provider_connection, app.repositories.
provider_connection_repository) — this EP adds the API layer on top. No
migration required.

Deliberately NOT built here: per-connection API key storage. The model's
own docstring says credentials belong in a Secrets store "by reference" —
no such store exists in this codebase yet, and storing raw secrets in a
new ad-hoc column would be worse than not building credential storage at
all. "Test connection" below reuses the existing GET /v1/providers/
{provider}/test connectivity probe, which authenticates via server-side
environment-variable credentials — the same real, working mechanism
apps/dashboard's Connections page already uses — rather than fabricating
a second, fake credential-testing path.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbDep
from app.api.v1.providers import _get_adapter, _require_supported
from app.auth.dependencies import RequirePermission
from app.auth.rbac import Permission
from app.db.mixins import uuid7
from app.models.membership import Membership
from app.models.provider_connection import ProviderConnection, ProviderHealthStatus, ProviderType
from app.providers.errors import AuthenticationError, InvalidRequestError, ProviderError
from app.repositories.provider_connection_repository import ProviderConnectionRepository
from app.schemas.provider_connections import (
    CreateProviderConnectionRequest,
    ProviderConnectionResponse,
    ProviderConnectionsListResponse,
    TestProviderConnectionResponse,
    UpdateProviderConnectionRequest,
)

router = APIRouter(
    prefix="/organizations/{org_id}/provider-connections", tags=["provider-connections"]
)


def _parse_provider_type(value: str) -> ProviderType:
    try:
        return ProviderType(value)
    except ValueError as exc:
        supported = [p.value for p in ProviderType]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid provider_type {value!r}. Must be one of: {supported}",
        ) from exc


def _to_response(conn: ProviderConnection) -> ProviderConnectionResponse:
    return ProviderConnectionResponse(
        id=conn.external_id,
        provider_type=conn.provider_type.value,
        display_name=conn.display_name,
        project_id=str(conn.project_id) if conn.project_id else None,
        is_active=conn.is_active,
        health_status=conn.health_status.value,
        last_failure_at=conn.last_failure_at,
        last_recovery_at=conn.last_recovery_at,
        consecutive_failure_count=conn.consecutive_failure_count,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


@router.get(
    "",
    response_model=ProviderConnectionsListResponse,
    summary="List provider connections in an organization",
)
async def list_provider_connections(
    org_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> ProviderConnectionsListResponse:
    repo = ProviderConnectionRepository(db)
    page = await repo.list_by_org(org_id, limit=100)
    return ProviderConnectionsListResponse(
        connections=[_to_response(c) for c in page.items],
        total=len(page.items),
    )


@router.post(
    "",
    response_model=ProviderConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a provider connection",
)
async def create_provider_connection(
    org_id: uuid.UUID,
    body: CreateProviderConnectionRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> ProviderConnectionResponse:
    conn = ProviderConnection()
    conn.id = uuid7()
    conn.organization_id = org_id
    conn.provider_type = _parse_provider_type(body.provider_type)
    conn.provider_name = body.provider_type
    conn.display_name = body.display_name
    conn.project_id = body.project_id
    conn.is_active = True
    conn.configuration = {}
    conn.health_status = ProviderHealthStatus.UNKNOWN

    repo = ProviderConnectionRepository(db)
    created = await repo.create(conn)
    return _to_response(created)


@router.patch(
    "/{connection_id}",
    response_model=ProviderConnectionResponse,
    summary="Update a provider connection",
)
async def update_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    body: UpdateProviderConnectionRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> ProviderConnectionResponse:
    repo = ProviderConnectionRepository(db)
    conn = await repo.get(connection_id)
    if conn is None or conn.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider connection not found"
        )

    updates = body.model_dump(exclude_unset=True)
    updated = await repo.update(conn, **updates) if updates else conn
    return _to_response(updated)


@router.delete(
    "/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a provider connection",
)
async def delete_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_DELETE)],
) -> None:
    repo = ProviderConnectionRepository(db)
    conn = await repo.get(connection_id)
    if conn is None or conn.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider connection not found"
        )
    await repo.soft_delete(conn)


@router.post(
    "/{connection_id}/test",
    response_model=TestProviderConnectionResponse,
    summary="Test a provider connection's connectivity",
    description=(
        "Reuses the same live connectivity probe as GET /v1/providers/{provider}/test "
        "(server-side environment-variable credentials) and persists the result onto "
        "this connection's health_status/last_failure_at/last_recovery_at/"
        "consecutive_failure_count fields."
    ),
)
async def test_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> TestProviderConnectionResponse:
    repo = ProviderConnectionRepository(db)
    conn = await repo.get(connection_id)
    if conn is None or conn.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider connection not found"
        )

    try:
        pt = _require_supported(conn.provider_type.value)
    except HTTPException:
        # Not yet a production-ready adapter (EP-06/EP-07 territory) — be
        # honest about it rather than faking a result.
        return TestProviderConnectionResponse(
            connection_id=conn.external_id,
            provider_type=conn.provider_type.value,
            health_status=conn.health_status.value,
            tested=False,
            detail=f"No production-ready adapter for {conn.provider_type.value!r} yet.",
        )

    adapter = _get_adapter(pt, with_key=True)
    now = datetime.now(UTC)
    try:
        await adapter.verify_auth()
        conn.health_status = ProviderHealthStatus.HEALTHY
        conn.last_recovery_at = now
        conn.consecutive_failure_count = 0
        detail = "Connection healthy."
    except (AuthenticationError, InvalidRequestError, ProviderError) as exc:
        conn.health_status = ProviderHealthStatus.CRITICAL
        conn.last_failure_at = now
        conn.consecutive_failure_count += 1
        detail = str(exc)

    await repo.update(
        conn,
        health_status=conn.health_status,
        last_failure_at=conn.last_failure_at,
        last_recovery_at=conn.last_recovery_at,
        consecutive_failure_count=conn.consecutive_failure_count,
    )

    return TestProviderConnectionResponse(
        connection_id=conn.external_id,
        provider_type=conn.provider_type.value,
        health_status=conn.health_status.value,
        tested=True,
        detail=detail,
    )
