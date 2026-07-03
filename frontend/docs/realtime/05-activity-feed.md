# Activity Feed

`frontend/src/components/LiveActivityFeed.tsx`, used on Overview in
place of the old static "Recent Activity" table (which had a
hard-coded, decorative "Live" pill that wasn't wired to anything real).

## Data sources, merged

1. **Live**: `useLiveActivity(limit)` — `usage.created` events from
   `useRealtimeStore.recentActivity`, already newest-first.
2. **Polled fallback**: `useRecentActivity(limit)` — the existing
   `GET /v1/usage/events`-backed hook. As documented in
   `services/api.ts`, this currently returns an empty list in live mode
   (the backend endpoint is `501 NOT IMPLEMENTED`); the feed still calls
   it so that once that endpoint ships, history shows up automatically
   with zero frontend changes.

Live rows take priority; a polled row with an id that's already present
among the live rows is deduplicated.

## Newest first

`useRealtimeStore.ingestEvent` prepends (`[event, ...prev]`), so live
rows arrive newest-first with no client-side sort needed.

## Pause on hover

`onMouseEnter` snapshots the currently-rendered rows into `frozenRows`
state and sets `paused = true`; while paused, the rendered list is the
frozen snapshot, not the live `recentActivity` — so a reader isn't
fighting a list that keeps reordering under their cursor while they're
trying to read or click a row. `onMouseLeave` clears the freeze and the
list resumes reflecting live data immediately.

## Row cap, not virtualization

`MAX_VISIBLE_ROWS = 25` by default (overridable via the `limit` prop —
Overview passes `10`). The underlying store buffer can hold up to 200
events, but only `limit` are ever rendered. This is a bounded-render
cap, **not** true windowed virtualization (no `react-window` or
similar) — documented here explicitly rather than claimed, since this
repo has no virtualization library and adding one for a list this size
wasn't judged worth the new dependency. If activity volume ever
justifies a genuinely long visible list, that's the point to reach for
one.

## Columns

Time, Provider (existing `ProviderBadge`), Model, Status, Cost. The
ticket's requested column list also named "Latency" and "Organization" —
both were deliberately dropped:
- **Latency**: `usage.created`'s payload
  (`backend/docs/realtime/04-event-model.md`) doesn't carry
  `latency_ms` — showing a column that's always empty would be a fake
  affordance.
- **Organization**: every row on this dashboard already belongs to the
  one currently-active organization (enforced by the backend's
  connection-level isolation); a column that's always the same value
  adds no information.

## Accessibility

The "Live"/"Polling" status pill uses `aria-live="polite"` so a screen
reader announces the transition without interrupting whatever the user
is doing. Rows use `<AnimatePresence>` with `layout` for smooth
reordering, respecting the app-wide `<MotionConfig reducedMotion="user">`
(EP-10) — animations are automatically disabled under
`prefers-reduced-motion`.
