# Notification Center — EP-19.3

Extends the EP-19.2 bell-menu notification panel
(`frontend/src/layouts/Header.tsx`) — no rewrite, additive only.

## Two data sources, kept distinct on purpose

1. **`useAlerts()`** (`frontend/src/hooks/useAlerts.ts`) — unchanged
   architecture from EP-19.2: client-derived budget/anomaly alerts +
   live-merged WebSocket events. This still backs the bell-menu's instant
   feed and unread badge.
2. **`useAlertsHistory()` / `useAlertActions()`**
   (`frontend/src/hooks/useAlertsHistory.ts`, new) — React Query wrapper
   around `GET /v1/alerts` (the persisted history) and the
   acknowledge/resolve/dismiss/reopen mutations. This is the "View
   history" / search surface; it only returns alert types the backend
   actually persists (the 6 wired types — see the architecture doc).

`DerivedAlert` (the shape `useAlerts()` returns) now carries an optional
`alertId` — threaded from `event.payload.alert_id`, which
`AlertService._publish()` always includes for a backend-fired alert.
Client-derived (budget/anomaly heuristic) alerts have no backend row, so
their `alertId` stays `undefined` — archiving those is local-only.

## What the panel supports

| Feature | Implementation |
|---|---|
| Unread count | `unreadCount` from `useAlerts()`, badge with 9+ cap |
| Read | Click a row → `useNotificationStore().markRead(id)` |
| Mark all read | Header button, `markAllRead(alerts.map(a => a.id))` |
| Dismiss | Per-row `X` button → local store only |
| **Archive** (new) | Per-row `Archive` icon → local dismiss + `POST /v1/alerts/{id}/dismiss` when `alertId` is present |
| **Search** (new) | Text input, filters the currently-loaded `alerts` list by title/description |
| **Filter — Severity** (new) | Dropdown (`danger`/`warning`/`info`), filters the same list |

Filter scope note: severity and free-text search are the two filter
dimensions actually implemented client-side over the bell menu's loaded
list (the ticket also names Date/Organization/Alert Type — Organization
is implicit since the panel is always scoped to the current org, and
Date/Alert-Type filtering is available on the REST history endpoint
`GET /v1/alerts` via `since`/`until`/`alert_type` query params for a
future dedicated history page, but not yet wired into the bell-menu UI
itself — stated rather than silently missing).

## Alert Timeline

`frontend/src/components/AlertTimeline.tsx` — Created → Acknowledged →
Resolved/Dismissed, animated, chronologically sorted. Reads directly off
an `AlertRecord`'s four timestamp fields (`first_occurred_at`,
`acknowledged_at`, `resolved_at`, `dismissed_at`). See the Backend
Architecture doc's "Timeline note" for why reopening doesn't erase an
earlier acknowledged/resolved step.

## Live updates

No polling anywhere in this path. `useAlerts()` merges events the moment
they arrive over the existing EP-19.1 WebSocket connection; the REST
history hook (`useAlertsHistory`) invalidates its React Query cache after
every mutation (acknowledge/resolve/archive/reopen), so a status change
made in one tab is visible on refetch, and the live event the backend
also publishes updates the bell-menu feed instantly regardless.
