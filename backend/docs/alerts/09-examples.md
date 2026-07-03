# Examples — EP-19.3

## Create a budget-threshold rule

```bash
curl -X POST "https://api.example.com/v1/alerts/rules?organization_id=$ORG_ID" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "budget_threshold",
    "name": "90% budget warning",
    "severity": "high",
    "operator": "gte",
    "threshold": "90",
    "enabled": true
  }'
```

Once created, every `POST /v1/ingest/usage` request against a project
with a `budget` set will evaluate this rule against month-to-date spend
(as a percentage of budget) and fire an alert the first time it crosses
90% — see `app/api/v1/ingest.py::_check_budget_alerts`.

## List and filter alert history

```bash
curl "https://api.example.com/v1/alerts?organization_id=$ORG_ID&status=open&severity=critical&search=budget" \
  -H "Authorization: Bearer $JWT"
```

## Acknowledge, resolve, dismiss, reopen

```bash
curl -X POST "https://api.example.com/v1/alerts/$ALERT_ID/acknowledge?organization_id=$ORG_ID" \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"reason": "Investigating with the infra team"}'

curl -X POST "https://api.example.com/v1/alerts/$ALERT_ID/resolve?organization_id=$ORG_ID" \
  -H "Authorization: Bearer $JWT"

curl -X POST "https://api.example.com/v1/alerts/$ALERT_ID/dismiss?organization_id=$ORG_ID" \
  -H "Authorization: Bearer $JWT"

curl -X POST "https://api.example.com/v1/alerts/$ALERT_ID/reopen?organization_id=$ORG_ID" \
  -H "Authorization: Bearer $JWT"
```

Each transition is status-guarded — `acknowledge` only from `open`,
`resolve`/`dismiss` from `open`/`acknowledged`, `reopen` from anything but
`open` — an invalid transition returns `409 Conflict`, not a silent
no-op.

## Suppress an organization-wide maintenance window

```bash
curl -X POST "https://api.example.com/v1/alerts/suppressions?organization_id=$ORG_ID" \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{
    "scope": "organization",
    "starts_at": "2026-07-10T02:00:00Z",
    "ends_at": "2026-07-10T04:00:00Z",
    "reason": "Scheduled database maintenance"
  }'
```

## Set your own preferences (quiet hours + severity floor)

```bash
curl -X PATCH "https://api.example.com/v1/alerts/preferences?organization_id=$ORG_ID" \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{
    "min_severity": "high",
    "quiet_hours_start": "22:00",
    "quiet_hours_end": "07:00",
    "timezone": "America/New_York"
  }'
```

## Firing an alert from a new backend call site (for future EPs)

```python
from app.alerts.dispatcher import AlertService
from app.alerts.dedup import provider_scope
from app.models.alert import AlertType, AlertSeverity

await AlertService(db, event_bus).fire(
    organization_id=org_id,
    alert_type=AlertType.PROVIDER_ERROR,
    severity=AlertSeverity.HIGH,
    title="OpenAI is failing",
    message="3 consecutive request failures against OpenAI.",
    source="provider_health_check",   # whatever subsystem calls this
    scope=provider_scope("openai"),
    metadata={"provider": "openai", "consecutive_failures": 3},
)
```

This is the entire integration surface a future EP needs — suppression,
dedup, persistence, and live delivery all happen automatically inside
`fire()`.

## Frontend: reading live alerts

```tsx
import { useAlerts } from "../hooks/useAlerts";

function MyComponent() {
  const { alerts, unreadCount } = useAlerts();
  // alerts merges client-derived budget/anomaly alerts with live
  // WebSocket-delivered backend alerts automatically.
}
```

## Frontend: acting on a persisted alert

```tsx
import { useAlertActions } from "../hooks/useAlertsHistory";

function AckButton({ alertId }: { alertId: string }) {
  const { acknowledge } = useAlertActions();
  return (
    <button onClick={() => acknowledge.mutate({ alertId, reason: "on it" })}>
      Acknowledge
    </button>
  );
}
```
