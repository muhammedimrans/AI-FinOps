"""Alerts API — EP-19.3.

Endpoints
---------
GET    /v1/alerts                          — history/search/filter
POST   /v1/alerts/{alert_id}/acknowledge   — OPEN -> ACKNOWLEDGED
POST   /v1/alerts/{alert_id}/resolve       — OPEN|ACKNOWLEDGED -> RESOLVED
POST   /v1/alerts/{alert_id}/dismiss       — OPEN|ACKNOWLEDGED -> DISMISSED
POST   /v1/alerts/{alert_id}/reopen        — ACKNOWLEDGED|RESOLVED|DISMISSED -> OPEN
GET    /v1/alerts/preferences              — the caller's own preferences (this org)
PATCH  /v1/alerts/preferences              — update (creates the row lazily)
GET    /v1/alerts/rules                    — list configured AlertRule rows
POST   /v1/alerts/rules                    — create a rule
DELETE /v1/alerts/rules/{rule_id}          — soft-delete a rule
GET    /v1/alerts/suppressions             — list configured suppressions
POST   /v1/alerts/suppressions             — create a suppression
DELETE /v1/alerts/suppressions/{id}        — soft-delete (ends it immediately)

Authorization
-------------
Every endpoint takes `organization_id` as a query parameter (matching the
dashboard/analytics-style routes, not the org_id-path-param style used by
app/api/v1/organizations.py) and is gated by RequireQueryPermission —
NOTIFICATION_READ for GETs, NOTIFICATION_WRITE for mutations. Membership
in that organization is always verified first (OrgScopedMembership, via
`app.auth.dependencies.get_query_org_membership`) — a client can never
read or mutate another organization's alerts by guessing an alert_id,
since every mutation re-checks `alert.organization_id == organization_id`
after lookup.

Timeline note: an Alert row is a single mutable record, not an append-only
event log — `first_occurred_at`/`acknowledged_at`/`resolved_at`/
`dismissed_at` are each set at most once per lifecycle pass and never
cleared by a later transition (including reopen), so a client can render
a simple chronological timeline from these four fields. This is
sufficient for the single-lifecycle-per-alert model this EP ships; a
true multi-cycle audit trail (reopened alerts re-acknowledged and
re-resolved) would need a separate append-only table, which is out of
scope here and stated rather than silently incomplete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts import metrics as alert_metrics
from app.alerts.preferences import get_or_default, minute_of_day
from app.api.deps import DbDep
from app.auth.dependencies import CurrentUser, RequireQueryPermission
from app.auth.rbac import Permission
from app.db.mixins import uuid7
from app.models.alert import (
    Alert,
    AlertOperator,
    AlertPreference,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    AlertSuppression,
    AlertType,
    SuppressionScope,
)
from app.repositories.alert_repository import (
    AlertPreferenceRepository,
    AlertRepository,
    AlertRuleRepository,
    AlertSuppressionRepository,
)
from app.schemas.alerts import (
    AcknowledgeAlertRequest,
    AlertPreferenceResponse,
    AlertResponse,
    AlertRuleResponse,
    AlertRulesListResponse,
    AlertsListResponse,
    AlertSuppressionResponse,
    AlertSuppressionsListResponse,
    CreateAlertRuleRequest,
    CreateAlertSuppressionRequest,
    UpdateAlertPreferenceRequest,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _parse_enum(enum_cls: type, value: str, field: str) -> object:
    try:
        return enum_cls(value)
    except ValueError as exc:
        valid = [m.value for m in enum_cls]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field} {value!r}. Must be one of: {valid}",
        ) from exc


def _to_alert_response(a: Alert) -> AlertResponse:
    return AlertResponse(
        id=a.id,
        alert_type=a.alert_type.value,
        severity=a.severity.value,
        status=a.status.value,
        title=a.title,
        message=a.message,
        source=a.source,
        occurrence_count=a.occurrence_count,
        metadata=a.alert_metadata,
        first_occurred_at=a.first_occurred_at,
        last_occurred_at=a.last_occurred_at,
        acknowledged_by=a.acknowledged_by,
        acknowledged_at=a.acknowledged_at,
        acknowledgement_reason=a.acknowledgement_reason,
        resolved_at=a.resolved_at,
        dismissed_at=a.dismissed_at,
        created_at=a.created_at,
    )


async def _get_org_alert(
    db: AsyncSession, organization_id: uuid.UUID, alert_id: uuid.UUID
) -> Alert:
    alert = await AlertRepository(db).get(alert_id)
    if alert is None or alert.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


# ── History / search / filter ─────────────────────────────────────────────────


@router.get(
    "",
    response_model=AlertsListResponse,
    summary="List/search alert history",
    description=(
        "Returns fired alerts for the organization, most recent first. "
        "Supports filtering by status, severity, alert_type, a created_at "
        "date range, and free-text search over title/message."
    ),
)
async def list_alerts(
    db: DbDep,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_READ)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    severity: Annotated[str | None, Query()] = None,
    alert_type: Annotated[str | None, Query()] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AlertsListResponse:
    parsed_status = _parse_enum(AlertStatus, status_filter, "status") if status_filter else None
    parsed_severity = _parse_enum(AlertSeverity, severity, "severity") if severity else None
    parsed_type = _parse_enum(AlertType, alert_type, "alert_type") if alert_type else None

    repo = AlertRepository(db)
    alerts = await repo.list_for_org(
        organization_id,
        status=parsed_status,
        severity=parsed_severity.value if parsed_severity else None,
        alert_type=parsed_type,
        since=since,
        until=until,
        search=search,
        limit=limit,
    )
    items = [_to_alert_response(a) for a in alerts]
    return AlertsListResponse(alerts=items, total=len(items))


# ── Acknowledgement lifecycle ─────────────────────────────────────────────────


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertResponse,
    summary="Acknowledge an open alert",
)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    body: AcknowledgeAlertRequest,
    db: DbDep,
    current_user: CurrentUser,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertResponse:
    repo = AlertRepository(db)
    alert = await _get_org_alert(db, organization_id, alert_id)
    if alert.status != AlertStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot acknowledge an alert in status {alert.status.value!r}",
        )
    updated = await repo.update(
        alert,
        status=AlertStatus.ACKNOWLEDGED,
        acknowledged_by=current_user.id,
        acknowledged_at=datetime.now(UTC),
        acknowledgement_reason=body.reason,
    )
    alert_metrics.alerts_acknowledged_total.labels(alert_type=updated.alert_type.value).inc()
    return _to_alert_response(updated)


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertResponse,
    summary="Resolve an alert",
)
async def resolve_alert(
    alert_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertResponse:
    repo = AlertRepository(db)
    alert = await _get_org_alert(db, organization_id, alert_id)
    if alert.status not in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot resolve an alert in status {alert.status.value!r}",
        )
    updated = await repo.update(
        alert, status=AlertStatus.RESOLVED, resolved_at=datetime.now(UTC)
    )
    return _to_alert_response(updated)


@router.post(
    "/{alert_id}/dismiss",
    response_model=AlertResponse,
    summary="Dismiss an alert",
)
async def dismiss_alert(
    alert_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertResponse:
    repo = AlertRepository(db)
    alert = await _get_org_alert(db, organization_id, alert_id)
    if alert.status not in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot dismiss an alert in status {alert.status.value!r}",
        )
    updated = await repo.update(
        alert, status=AlertStatus.DISMISSED, dismissed_at=datetime.now(UTC)
    )
    return _to_alert_response(updated)


@router.post(
    "/{alert_id}/reopen",
    response_model=AlertResponse,
    summary="Reopen an acknowledged, resolved, or dismissed alert",
)
async def reopen_alert(
    alert_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertResponse:
    repo = AlertRepository(db)
    alert = await _get_org_alert(db, organization_id, alert_id)
    if alert.status == AlertStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Alert is already open"
        )
    updated = await repo.update(alert, status=AlertStatus.OPEN)
    return _to_alert_response(updated)


# ── Preferences ────────────────────────────────────────────────────────────────


def _minute_to_hhmm(minute: int | None) -> str | None:
    if minute is None:
        return None
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _hhmm_to_minute(value: str | None) -> int | None:
    if not value:
        return None
    hour_str, _, minute_str = value.partition(":")
    return minute_of_day(time(hour=int(hour_str), minute=int(minute_str)))


def _to_preference_response(p: AlertPreference) -> AlertPreferenceResponse:
    return AlertPreferenceResponse(
        enabled_alert_types=p.enabled_alert_types,
        min_severity=p.min_severity.value,
        quiet_hours_start=_minute_to_hhmm(p.quiet_hours_start_minute),
        quiet_hours_end=_minute_to_hhmm(p.quiet_hours_end_minute),
        timezone=p.timezone,
        daily_digest=p.daily_digest,
        immediate_notifications=p.immediate_notifications,
        max_notifications=p.max_notifications,
    )


@router.get(
    "/preferences",
    response_model=AlertPreferenceResponse,
    summary="Get the caller's own alert preferences for this organization",
)
async def get_preferences(
    db: DbDep,
    current_user: CurrentUser,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_READ)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertPreferenceResponse:
    pref = await get_or_default(db, organization_id=organization_id, user_id=current_user.id)
    return _to_preference_response(pref)


@router.patch(
    "/preferences",
    response_model=AlertPreferenceResponse,
    summary="Update the caller's own alert preferences for this organization",
    description="Creates the preference row on first write (lazy creation).",
)
async def update_preferences(
    body: UpdateAlertPreferenceRequest,
    db: DbDep,
    current_user: CurrentUser,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertPreferenceResponse:
    repo = AlertPreferenceRepository(db)
    existing = await repo.get_for_user(organization_id, current_user.id)

    updates: dict[str, object] = {}
    if body.enabled_alert_types is not None:
        for t in body.enabled_alert_types:
            _parse_enum(AlertType, t, "enabled_alert_types")
        updates["enabled_alert_types"] = body.enabled_alert_types
    if body.min_severity is not None:
        updates["min_severity"] = _parse_enum(AlertSeverity, body.min_severity, "min_severity")
    if body.quiet_hours_start is not None:
        updates["quiet_hours_start_minute"] = _hhmm_to_minute(body.quiet_hours_start)
    if body.quiet_hours_end is not None:
        updates["quiet_hours_end_minute"] = _hhmm_to_minute(body.quiet_hours_end)
    if body.timezone is not None:
        updates["timezone"] = body.timezone
    if body.daily_digest is not None:
        updates["daily_digest"] = body.daily_digest
    if body.immediate_notifications is not None:
        updates["immediate_notifications"] = body.immediate_notifications
    if body.max_notifications is not None:
        updates["max_notifications"] = body.max_notifications

    if existing is None:
        default = await get_or_default(db, organization_id=organization_id, user_id=current_user.id)
        default.id = uuid7()
        for key, value in updates.items():
            setattr(default, key, value)
        created = await repo.create(default)
        return _to_preference_response(created)

    updated = await repo.update(existing, **updates)
    return _to_preference_response(updated)


# ── Rules ──────────────────────────────────────────────────────────────────────


def _to_rule_response(r: AlertRule) -> AlertRuleResponse:
    return AlertRuleResponse(
        id=r.id,
        alert_type=r.alert_type.value,
        name=r.name,
        severity=r.severity.value,
        operator=r.operator.value,
        threshold=str(r.threshold),
        enabled=r.enabled,
        created_at=r.created_at,
    )


@router.get(
    "/rules",
    response_model=AlertRulesListResponse,
    summary="List configured alert rules",
)
async def list_rules(
    db: DbDep,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_READ)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertRulesListResponse:
    rules = await AlertRuleRepository(db).list_for_org(organization_id)
    items = [_to_rule_response(r) for r in rules]
    return AlertRulesListResponse(rules=items, total=len(items))


@router.post(
    "/rules",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert rule",
    description=(
        "Only budget_threshold and budget_exceeded are evaluated against "
        "real data today (see app/alerts/rule_engine.py); a rule for any "
        "other alert_type can be created and stored but nothing currently "
        "evaluates it."
    ),
)
async def create_rule(
    body: CreateAlertRuleRequest,
    db: DbDep,
    current_user: CurrentUser,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertRuleResponse:
    alert_type = _parse_enum(AlertType, body.alert_type, "alert_type")
    severity = _parse_enum(AlertSeverity, body.severity, "severity")
    operator = _parse_enum(AlertOperator, body.operator, "operator")
    try:
        threshold = Decimal(body.threshold)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="threshold must be a valid decimal number",
        ) from exc

    rule = AlertRule(
        id=uuid7(),
        organization_id=organization_id,
        alert_type=alert_type,
        name=body.name,
        severity=severity,
        operator=operator,
        threshold=threshold,
        enabled=body.enabled,
        created_by=current_user.id,
    )
    created = await AlertRuleRepository(db).create(rule)
    return _to_rule_response(created)


@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an alert rule",
)
async def delete_rule(
    rule_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> None:
    repo = AlertRuleRepository(db)
    rule = await repo.get(rule_id)
    if rule is None or rule.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    await repo.soft_delete(rule)


# ── Suppressions ───────────────────────────────────────────────────────────────


def _to_suppression_response(s: AlertSuppression) -> AlertSuppressionResponse:
    return AlertSuppressionResponse(
        id=s.id,
        scope=s.scope.value,
        target=s.target,
        starts_at=s.starts_at,
        ends_at=s.ends_at,
        reason=s.reason,
        created_at=s.created_at,
    )


@router.get(
    "/suppressions",
    response_model=AlertSuppressionsListResponse,
    summary="List configured alert suppressions",
)
async def list_suppressions(
    db: DbDep,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_READ)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertSuppressionsListResponse:
    suppressions = await AlertSuppressionRepository(db).list_for_org(organization_id)
    items = [_to_suppression_response(s) for s in suppressions]
    return AlertSuppressionsListResponse(suppressions=items, total=len(items))


@router.post(
    "/suppressions",
    response_model=AlertSuppressionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a suppression window",
    description=(
        "scope='organization' suppresses every alert type org-wide "
        "(e.g. a maintenance window) and ignores `target`. "
        "scope='alert_type' requires `target` to be a valid AlertType "
        "value. scope='provider' requires `target` to be a provider slug. "
        "Leave `ends_at` unset for an indefinite suppression."
    ),
)
async def create_suppression(
    body: CreateAlertSuppressionRequest,
    db: DbDep,
    current_user: CurrentUser,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> AlertSuppressionResponse:
    scope = _parse_enum(SuppressionScope, body.scope, "scope")
    if scope == SuppressionScope.ALERT_TYPE and body.target is not None:
        _parse_enum(AlertType, body.target, "target")

    suppression = AlertSuppression(
        id=uuid7(),
        organization_id=organization_id,
        scope=scope,
        target=body.target,
        starts_at=body.starts_at or datetime.now(UTC),
        ends_at=body.ends_at,
        reason=body.reason,
        created_by=current_user.id,
    )
    created = await AlertSuppressionRepository(db).create(suppression)
    return _to_suppression_response(created)


@router.delete(
    "/suppressions/{suppression_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete (immediately end) a suppression",
)
async def delete_suppression(
    suppression_id: uuid.UUID,
    db: DbDep,
    _member: Annotated[
        object, RequireQueryPermission(Permission.NOTIFICATION_WRITE)
    ],
    organization_id: Annotated[uuid.UUID, Query(description="Organization ID")],
) -> None:
    repo = AlertSuppressionRepository(db)
    suppression = await repo.get(suppression_id)
    if suppression is None or suppression.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found"
        )
    await repo.soft_delete(suppression)
