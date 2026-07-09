# Performance Guide

## Ticket targets

| Target | Status |
|---|---|
| 10,000 streamed events/hour | Architecturally fine (see below) — **not load-tested** in this sandbox, same honest caveat as the backend's own EP-19.1 report. |
| 60 FPS animations | Relies on Framer Motion + `<MotionConfig reducedMotion="user">` (pre-existing, EP-10) — not independently profiled in this EP. |
| Minimal re-rendering | See "Batched updates" below. |
| Memory stable after 24h | `recentActivity` is hard-capped at `activityLimit` (200); no unbounded array anywhere in the real-time layer. Not verified with an actual 24h soak test — see [Testing](../../backend/docs/realtime/06-scaling.md)'s parallel honesty note on the backend side. |

## Batched updates, not per-event re-renders

- **Debounced query invalidation**: `useRealtimeQueryBridge` waits
  1.5s of quiet after the last `usage.created` event before invalidating
  any dashboard query — a burst of events (e.g. several requests landing
  within the same second) triggers one refetch, not one per event.
- **Zustand selector subscriptions**: every `useRealtimeStore` consumer
  (`useConnectionStatus`, `useLiveActivity`, `useLiveMetrics`, etc.)
  subscribes to a narrow selector, so a component reading only
  `connection.status` doesn't re-render when `recentActivity` changes,
  and vice versa.
- **Capped activity buffer**: `recentActivity` never grows past
  `activityLimit` (200) regardless of connection uptime or event volume
  — `Array.prototype.slice` on every `ingestEvent` call, not an
  unbounded push.

## Dispatch latency, frontend side

Once a `RealtimeEvent` frame arrives over the WebSocket, `client.ts`
parses it synchronously and calls `onEvent` synchronously — there is no
`setTimeout`/microtask hop between "frame received" and "store updated."
The perceptible end-to-end latency (backend publish → frontend UI
update) is dominated by network/backend dispatch time (see the
backend's own `docs/realtime/06-scaling.md`), not anything added on the
frontend.

## Rendering cost of the activity feed

Capped at a small visible row count (`MAX_VISIBLE_ROWS = 25`, Overview
uses 10) rather than true windowed virtualization — see
[Activity Feed](./05-activity-feed.md#row-cap-not-virtualization) for
why, stated as a real scoping decision rather than an oversight.

## What wasn't measured in this environment

This sandbox has no dedicated load-testing or profiling infrastructure
(no synthetic 10,000-client harness, no React DevTools Profiler CI gate,
no 24-hour soak runner). The architecture — bounded buffers, debounced
invalidation, narrow Zustand selectors — is what makes the ticket's
targets plausible on real infrastructure, but claiming they were
measured here would be dishonest. This mirrors the same caveat the
backend's EP-19.1 report gave for its own 10,000-connection target.
