# Notification Center

`hooks/useAlerts.ts`, rendered in `layouts/Header.tsx`'s bell popover.
Pre-existing before this EP as a purely **client-derived** panel
(budget-utilization alerts and spend anomalies computed from already-
cached dashboard query data — see EP-13's audit notes). This EP adds a
second source without touching the first.

## Two sources, one list

```
budget/anomaly alerts (derived, unchanged from before this EP)
                    +
live notification-shaped real-time events
                    =
useAlerts().alerts  (merged, sorted unread-first, dismissed ones filtered out)
```

Live events are filtered to a fixed set of notification-worthy types
(everything except `usage.created`/`usage.updated`, which belong to the
[Activity Feed](./05-activity-feed.md) instead):

`budget.threshold_reached`, `budget.exceeded`, `provider.error`,
`provider.recovery`, `sdk.connected`, `sdk.disconnected`,
`api_key.created`, `api_key.deleted`, `notification.created`.

## Honesty note — most of this is wired but currently silent

As of this EP, the backend **only actually emits `usage.created`** (see
`backend/docs/realtime/04-event-model.md`'s own accounting). None of
the 9 notification-shaped types above have a real trigger anywhere in
the backend yet. This means:

- The merge logic, the read/dismiss state, the UI — all real, all
  tested (`frontend/src/hooks/useAlerts.ts`,
  `frontend/src/__tests__/notifications.test.ts`).
- It will produce **zero** "live" category alerts in production today,
  because nothing publishes those event types yet.
- This is a deliberate, stated design choice — matching this whole
  session's pattern of building genuinely-correct plumbing ahead of a
  trigger that a later Engineering Package will add, rather than faking
  a trigger to make the feature look more finished than it is.

`describePayload()` in `useAlerts.ts` degrades gracefully for these
types too: since none of them have a backend-defined payload shape yet
(only `usage.created` does), it looks for common fields
(`message`/`description`/`reason`/`provider`/`name`) and falls back to
just a timestamp rather than assuming a shape that might not match
whatever a later EP actually ships.

## Read / dismiss / clear all / unread badge

All four ticket-named affordances, in `stores/notifications.ts`:

| Action | Effect |
|---|---|
| Click an alert row | `markRead(id)` — dims it, no longer counts toward the unread badge. |
| "Mark all read" (header) | `markAllRead(ids)` for every currently-visible alert. |
| Hover → X button (per row) | `dismiss(id)` — hides that one alert entirely (independent of read state). |
| "Clear all" (header) | `clearAll(ids)` — dismisses every currently-visible alert. |
| Unread count | `alerts.filter(a => !a.read).length`, shown as the bell's badge. |

Both `readIds` and `dismissedIds` persist to `localStorage`
(`costorah-notifications`), so state survives a reload — for a live
event, its `event_id` is globally unique, so a dismissed live alert
never reappears.
