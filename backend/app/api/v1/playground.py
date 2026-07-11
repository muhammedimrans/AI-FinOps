"""AI Playground API — EP-25.4.

Endpoints (all under /v1/organizations/{org_id}/playground):
  GET    connections                        — connections usable in Playground
  GET    connections/{conn_id}/models       — live model catalog for one connection
  POST   execute                            — single-provider chat
  POST   compare                            — multi-provider Comparison Mode
  GET    history                            — search/filter history
  GET    history/{execution_id}             — one execution
  DELETE history/{execution_id}             — delete one history row
  POST   history/{execution_id}/rerun       — re-run a past prompt

Authorization: every endpoint requires `Permission.PROVIDER_READ` — granted
to every role including VIEWER (app.auth.rbac). Playground *uses* an
already-connected credential, it never creates/mutates/deletes a
ProviderConnection (that remains PROVIDER_WRITE/PROVIDER_DELETE-gated on
the Connections page, unchanged) — the same "read the resource, don't
manage it" boundary VIEWER already has everywhere else in this app. See
CLAUDE.md's EP-25.4 section for the full reasoning.

Personal vs. Business (EP-25.1): no special-casing needed here — a
Personal account's requests already flow through its one hidden personal
organization exactly like every other resource in this codebase since
EP-25.1; RBAC's structural OWNER-bypass (§29) already grants that account
every permission on its own org, including this one.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.dispatcher import AlertService
from app.api.deps import DbDep, EventBusDep
from app.auth.dependencies import CurrentUser, RequirePermission
from app.auth.rbac import Permission
from app.budgets.service import BudgetEvaluationService
from app.models.membership import Membership
from app.models.provider_connection import ProviderConnection
from app.providers.factory import ProviderFactory
from app.providers.registry import get_registry
from app.providers.validation import build_provider_config
from app.realtime.event_bus import EventBus
from app.repositories.playground_execution_repository import PlaygroundExecutionRepository
from app.repositories.provider_connection_repository import ProviderConnectionRepository
from app.schemas.playground import (
    ComparePlaygroundRequest,
    ComparePlaygroundResponse,
    ExecutePlaygroundRequest,
    PlaygroundConnectionOption,
    PlaygroundConnectionsResponse,
    PlaygroundExecutionResponse,
    PlaygroundHistoryResponse,
    PlaygroundModelInfo,
)
from app.services.playground_service import PlaygroundService
from app.services.provider_credential_service import ProviderCredentialService

router = APIRouter(prefix="/organizations/{org_id}/playground", tags=["playground"])

log = structlog.get_logger(__name__)

_credentials = ProviderCredentialService()


async def _get_connection(
    db: AsyncSession, org_id: uuid.UUID, connection_id: uuid.UUID
) -> ProviderConnection:
    conn = await ProviderConnectionRepository(db).get(connection_id)
    if conn is None or conn.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    return conn


def _to_response(execution: object) -> PlaygroundExecutionResponse:
    return PlaygroundExecutionResponse.model_validate(execution, from_attributes=True)


async def _evaluate_budgets(db: AsyncSession, event_bus: EventBus, org_id: uuid.UUID) -> None:
    """Same post-usage hook ProviderSyncService's manual-sync path and the
    background scheduler both already call — a Playground request is real
    usage, so it gets the same treatment (EP-24.2)."""
    try:
        alert_service = AlertService(db, event_bus)
        evaluator = BudgetEvaluationService(db, alert_service=alert_service)
        await evaluator.evaluate_and_alert(org_id)
    except Exception:
        log.warning(
            "playground_budget_evaluation_failed", organization_id=str(org_id), exc_info=True
        )


@router.get(
    "/connections",
    response_model=PlaygroundConnectionsResponse,
    summary="List provider connections usable in the Playground",
)
async def list_playground_connections(
    org_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> PlaygroundConnectionsResponse:
    repo = ProviderConnectionRepository(db)
    page = await repo.list_by_org(org_id, limit=100)
    return PlaygroundConnectionsResponse(
        connections=[
            PlaygroundConnectionOption(
                id=c.id,
                provider_type=c.provider_type.value,
                display_name=c.display_name,
                is_active=c.is_active,
                has_credential=c.encrypted_api_key is not None,
                last_validation_status=(
                    c.last_validation_status.value if c.last_validation_status else None
                ),
            )
            for c in page.items
        ]
    )


@router.get(
    "/connections/{connection_id}/models",
    response_model=list[PlaygroundModelInfo],
    summary="Live model catalog for one connection",
)
async def list_playground_models(
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> list[PlaygroundModelInfo]:
    """Reuses each adapter's own `list_models()` — the exact same live
    catalog call the Connections page already shows (EP-26.0.1/26.0.2) —
    never a second, Playground-specific model list."""
    conn = await _get_connection(db, org_id, connection_id)
    api_key = _credentials.decrypt(conn.encrypted_api_key) if conn.encrypted_api_key else None
    config = build_provider_config(conn.provider_type, api_key=api_key, base_url=conn.base_url)
    adapter = ProviderFactory(get_registry()).create(config)
    try:
        models = await adapter.list_models()
    finally:
        await adapter.aclose()
    return [
        PlaygroundModelInfo(
            id=m.id,
            display_name=m.display_name,
            context_window=m.context_window,
            max_output_tokens=m.max_output_tokens,
            capabilities=[c.value for c in m.capabilities],
            input_cost_per_1k=m.input_cost_per_1k,
            output_cost_per_1k=m.output_cost_per_1k,
            is_deprecated=m.is_deprecated,
        )
        for m in models
    ]


@router.post(
    "/execute",
    response_model=PlaygroundExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send one prompt to one connected provider",
)
async def execute_playground(
    org_id: uuid.UUID,
    body: ExecutePlaygroundRequest,
    db: DbDep,
    event_bus: EventBusDep,
    current_user: CurrentUser,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> PlaygroundExecutionResponse:
    conn = await _get_connection(db, org_id, body.provider_connection_id)
    service = PlaygroundService(db)
    execution = await service.execute(
        organization_id=org_id,
        user_id=current_user.id,
        connection=conn,
        project_id=body.project_id,
        model_id=body.model_id,
        system_prompt=body.system_prompt,
        user_prompt=body.user_prompt,
        temperature=body.temperature,
        top_p=body.top_p,
        max_tokens=body.max_tokens,
    )
    await db.commit()
    await _evaluate_budgets(db, event_bus, org_id)
    return _to_response(execution)


@router.post(
    "/compare",
    response_model=ComparePlaygroundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send the same prompt to several connections at once (Comparison Mode)",
)
async def compare_playground(
    org_id: uuid.UUID,
    body: ComparePlaygroundRequest,
    db: DbDep,
    event_bus: EventBusDep,
    current_user: CurrentUser,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> ComparePlaygroundResponse:
    from app.db.mixins import uuid7

    comparison_group_id = uuid7()
    service = PlaygroundService(db)
    executions = []
    # Sequential, not asyncio.gather — every connection may share the same
    # AsyncSession, which SQLAlchemy's async engine does not support
    # concurrent use of; one connection's slow provider never blocks this
    # from returning the others' real results, just serially rather than
    # in parallel.
    for target in body.targets:
        model_id = body.model_ids.get(str(target))
        if not model_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"No model_id supplied for connection {target}",
            )
        conn = await _get_connection(db, org_id, target)
        execution = await service.execute(
            organization_id=org_id,
            user_id=current_user.id,
            connection=conn,
            project_id=body.project_id,
            model_id=model_id,
            system_prompt=body.system_prompt,
            user_prompt=body.user_prompt,
            temperature=body.temperature,
            top_p=body.top_p,
            max_tokens=body.max_tokens,
            comparison_group_id=comparison_group_id,
        )
        executions.append(execution)
    await db.commit()
    await _evaluate_budgets(db, event_bus, org_id)
    return ComparePlaygroundResponse(
        comparison_group_id=comparison_group_id,
        executions=[_to_response(e) for e in executions],
    )


@router.get(
    "/history",
    response_model=PlaygroundHistoryResponse,
    summary="Search/filter Playground execution history",
)
async def list_playground_history(
    org_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
    mine_only: bool = Query(default=False),
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PlaygroundHistoryResponse:
    repo = PlaygroundExecutionRepository(db)
    executions, total = await repo.list_for_org(
        org_id,
        user_id=current_user.id if mine_only else None,
        provider=provider,
        model=model,
        search=search,
        limit=limit,
        offset=offset,
    )
    return PlaygroundHistoryResponse(executions=[_to_response(e) for e in executions], total=total)


@router.get(
    "/history/{execution_id}",
    response_model=PlaygroundExecutionResponse,
    summary="Get one Playground execution",
)
async def get_playground_execution(
    org_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> PlaygroundExecutionResponse:
    repo = PlaygroundExecutionRepository(db)
    execution = await repo.get_for_org(org_id, execution_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return _to_response(execution)


@router.delete(
    "/history/{execution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one Playground history row",
)
async def delete_playground_execution(
    org_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> None:
    repo = PlaygroundExecutionRepository(db)
    execution = await repo.get_for_org(org_id, execution_id)
    if execution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    await repo.soft_delete(execution)
    await db.commit()


@router.post(
    "/history/{execution_id}/rerun",
    response_model=PlaygroundExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Re-run a past prompt against the same connection/model",
)
async def rerun_playground_execution(
    org_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: DbDep,
    event_bus: EventBusDep,
    current_user: CurrentUser,
    _member: Annotated[Membership, RequirePermission(Permission.PROVIDER_READ)],
) -> PlaygroundExecutionResponse:
    repo = PlaygroundExecutionRepository(db)
    original = await repo.get_for_org(org_id, execution_id)
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    conn = await _get_connection(db, org_id, original.provider_connection_id)
    service = PlaygroundService(db)
    execution = await service.execute(
        organization_id=org_id,
        user_id=current_user.id,
        connection=conn,
        project_id=original.project_id,
        model_id=original.model,
        system_prompt=original.system_prompt,
        user_prompt=original.user_prompt,
        temperature=float(original.temperature) if original.temperature is not None else None,
        top_p=float(original.top_p) if original.top_p is not None else None,
        max_tokens=original.max_tokens,
    )
    await db.commit()
    await _evaluate_budgets(db, event_bus, org_id)
    return _to_response(execution)
