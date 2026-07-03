# User Preferences — EP-19.3

`app/alerts/preferences.py` + `AlertPreference` model
(`app/models/alert.py`) + `GET`/`PATCH /v1/alerts/preferences`.

## Storage

One row per `(organization_id, user_id)` — unique index enforced at the
DB level. Created **lazily**: `get_or_default()` returns an unsaved,
in-memory default the first time a user's preferences are read, and a row
is only persisted the first time they actually change a setting (via the
PATCH endpoint). No setup step required, no wasted rows for users who
never touch their settings.

## Fields

| Field | Type | Default | Meaning |
|---|---|---|---|
| `enabled_alert_types` | `list[str]` | `[]` | Empty = all types enabled |
| `min_severity` | `AlertSeverity` | `info` | Severity floor — see `should_surface()` |
| `quiet_hours_start_minute` / `_end_minute` | `int \| None` | `None` | Minutes since midnight; `None` disables quiet hours |
| `timezone` | `str` | `"UTC"` | Informational — quiet-hours math is done against whatever `now` the caller supplies |
| `daily_digest` | `bool` | `False` | **Stored, not built** — see below |
| `immediate_notifications` | `bool` | `True` | **Stored, not built** — see below |
| `max_notifications` | `int \| None` | `None` | Retention cap — stored, not enforced by a background job yet |

The ticket asks for these fields to exist ("stored, not built" for
future webhook/email integration) — they're all real columns with real
GET/PATCH support today; what's honestly not built is a digest-sending
job or a notification-volume enforcer, since there's no email/webhook
transport in this backend to send through (explicitly out of scope per
the ticket).

## Where preferences are applied — and where they aren't

`should_surface(preference, alert) -> bool` checks severity threshold and
type allow-list. **Applied at read time** (the `GET /v1/alerts` history
endpoint a client calls), **not at publish time**. This is a deliberate
consequence of EP-19.1's connection manager being purely
organization-scoped: every WebSocket connection for an org receives every
event for that org — there is no per-user routing layer to hook
preference filtering into without building new infrastructure the ticket
doesn't ask for. What preferences *do* gate is what a history query
returns for a given caller, and (if a future EP adds a digest job) what a
daily digest would include.

## Quiet hours

`is_within_quiet_hours(preference, now)` handles a window that wraps
midnight (e.g. `22:00`–`07:00`) by comparing against the wrap rather than
assuming `start < end` — tested explicitly (see
`tests/test_ep19_3.py::TestPreferences::test_quiet_hours_normal_window`).
Quiet hours affect whether an *immediate* notification should be pushed,
not whether an alert is visible in history — a user should always be able
to see what happened while quiet hours were active.

## Frontend `AlertPreferences` shape

`quiet_hours_start`/`quiet_hours_end` are serialized as `"HH:MM"` strings
over the wire (`_minute_to_hhmm()`/`_hhmm_to_minute()` in
`app/api/v1/alerts.py`) rather than raw minute integers — a friendlier
API surface for a settings form to bind to directly.
