"""Provider Connections API — EP-22.

Endpoints:
  GET    /v1/organizations/{org_id}/provider-connections                 — list
  POST   /v1/organizations/{org_id}/provider-connections                 — create (+ validate)
  PATCH  /v1/organizations/{org_id}/provider-connections/{conn_id}       — update metadata
  DELETE /v1/organizations/{org_id}/provider-connections/{conn_id}       — soft-delete
  POST   /v1/organizations/{org_id}/provider-connections/{conn_id}/test  — re-run validation
  POST   /v1/organizations/{org_id}/provider-connections/{conn_id}/rotate — replace the API key

Authorization: PROVIDER_READ / PROVIDER_WRITE / PROVIDER_DELETE — all
already defined in app.auth.rbac (EP-13), no changes needed.

As of EP-22, a connection can hold a real, per-connection, encrypted API
key (``ProviderConnection.encrypted_api_key``) — see
``app.security.encryption.EncryptionService`` for how it's encrypted at
rest and ``app.providers.validation.ProviderValidator`` for how it's
validated live against the provider. No response in this router ever
serializes the decrypted key — see ``_to_response``'s use of
``ProviderCredentialService.masked``. Full architecture: CLAUDE.md §13.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbDep
from app.auth.dependencies import RequirePermission
from app.auth.rbac import Permission
from app.db.mixins import uuid7
from app.models.membership import Membership
from app.models.provider_connection import ProviderConnection, ProviderType
from app.repositories.provider_connection_repository import ProviderConnectionRepository
from app.schemas.provider_connections import (
    CreateProviderConnectionRequest,
    ProviderConnectionResponse,
    ProviderConnectionsListResponse,
    RotateProviderConnectionKeyRequest,
    TestProviderConnectionResponse,
    UpdateProviderConnectionRequest,
)
from app.services.provider_credential_service import ProviderCredentialService
from app.services.provider_health_service import ProviderHealthService

router = APIRouter(
    prefix="/organizations/{org_id}/provider-connections", tags=["provider-connections"]
)

_credentials = ProviderCredentialService()
_health = ProviderHealthService()


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
        has_credential=conn.encrypted_api_key is not None,
        masked_api_key=_credentials.masked(conn.encrypted_api_key),
        base_url=conn.base_url,
        health_status=conn.health_status.value,
        last_validation_status=(
            conn.last_validation_status.value if conn.last_validation_status else None
        ),
        last_error=conn.last_error,
        last_failure_at=conn.last_failure_at,
        last_recovery_at=conn.last_recovery_at,
        consecutive_failure_count=conn.consecutive_failure_count,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


async def _get_owned_connection(
    repo: ProviderConnectionRepository, org_id: uuid.UUID, connection_id: uuid.UUID
) -> ProviderConnection:
    conn = await repo.get(connection_id)
    if conn is None or conn.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Provider connection not found"
        )
    return conn


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
    pt = _parse_provider_type(body.provider_type)

    conn = ProviderConnection()
    conn.id = uuid7()
    conn.organization_id = org_id
    conn.provider_type = pt
    conn.provider_name = body.provider_type
    conn.display_name = body.display_name
    conn.project_id = body.project_id
    conn.base_url = body.base_url
    conn.is_active = True
    conn.configuration = {}
    conn.encrypted_api_key = _credentials.encrypt(body.api_key) if body.api_key else None

    repo = ProviderConnectionRepository(db)
    created = await repo.create(conn)

    # EP-22 Part 3: validate immediately on save, whenever there's something
    # to validate (a credential, or a no-credential-required provider like
    # Ollama) — a freshly created connection should never sit at "unknown"
    # when we could have told the user right away whether it works.
    if body.api_key or pt == ProviderType.OLLAMA:
        await _health.check_and_persist(
            repo, created, api_key=body.api_key, base_url=created.base_url
        )

    return _to_response(created)


@router.patch(
    "/{connection_id}",
    response_model=ProviderConnectionResponse,
    summary="Update a provider connection's metadata",
)
async def update_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    body: UpdateProviderConnectionRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> ProviderConnectionResponse:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)

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
    conn = await _get_owned_connection(repo, org_id, connection_id)
    await repo.soft_delete(conn)


@router.post(
    "/{connection_id}/test",
    response_model=TestProviderConnectionResponse,
    summary="Test a provider connection (live validation)",
    description=(
        "Decrypts this connection's stored credential (if any) and runs a live "
        "validation call against the provider (EP-22 Part 3 — see the per-provider "
        "probe endpoint table in CLAUDE.md §13), persisting the result onto "
        "health_status / last_validation_status / last_error / "
        "last_failure_at / last_recovery_at / consecutive_failure_count."
    ),
)
async def test_provider_connection(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> TestProviderConnectionResponse:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)

    api_key = _credentials.decrypt(conn.encrypted_api_key) if conn.encrypted_api_key else None
    result = await _health.check_and_persist(repo, conn, api_key=api_key, base_url=conn.base_url)

    return TestProviderConnectionResponse(
        connection_id=conn.external_id,
        provider_type=conn.provider_type.value,
        health_status=result.health_status.value,
        last_validation_status=result.validation_status.value,
        tested=True,
        detail=result.detail,
    )


@router.post(
    "/{connection_id}/rotate",
    response_model=ProviderConnectionResponse,
    summary="Rotate a provider connection's API key",
    description=(
        "Replaces the stored credential and immediately re-validates it. The "
        "previous key is never returned or logged — only its encrypted form is "
        "overwritten. updated_at (and, once validation completes, "
        "last_recovery_at/last_failure_at) record the rotation for audit purposes."
    ),
)
async def rotate_provider_connection_key(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    body: RotateProviderConnectionKeyRequest,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_WRITE)],
) -> ProviderConnectionResponse:
    repo = ProviderConnectionRepository(db)
    conn = await _get_owned_connection(repo, org_id, connection_id)

    updated = await repo.update(conn, encrypted_api_key=_credentials.encrypt(body.api_key))
    await _health.check_and_persist(repo, updated, api_key=body.api_key, base_url=updated.base_url)
    return _to_response(updated)
