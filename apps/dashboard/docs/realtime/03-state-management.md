# State Management

## `useRealtimeStore` (Zustand)

`frontend/src/realtime/store.ts`. Ephemeral — not persisted to
`localStorage` (unlike `useAuthStore`/`useOrgStore`/`useThemeStore`),
since live connection state has no meaning across a page reload.

| Field | Type | Purpose |
|---|---|---|
| `connection` | `ConnectionSnapshot` | Status, organization id, reconnect attempts, heartbeat timing, last error — everything `ConnectionIndicator` renders. |
| `recentActivity` | `RealtimeEvent[]` | Newest-first, capped at `activityLimit` (default 200). The frontend's own local "replay buffer" — see [Connection Lifecycle](./04-connection-lifecycle.md#no-gap-fill-replay-on-reconnect) for what this is *not* a substitute for. |
| `lastEventByType` | `Partial<Record<EventType, RealtimeEvent>>` | O(1) lookup for "what was the last X event" without scanning `recentActivity`. |
| `liveMetrics` | `{ costDelta, tokensDelta, requestCount, providersSeen, modelsSeen }` | Accumulated since the socket last (re)connected — a *delta* to acknowledge live activity with (see Overview's "live since you opened this page" strip), never blended into the authoritative polled KPI numbers. |

## Why deltas aren't blended into KPI values

`MetricCard` already animates value transitions smoothly via
`useCountUp` (pre-existing, EP-10). Rather than hand-computing "polled
total + unconfirmed live delta, reset at some point after refetch" —
which risks double-counting if the reset timing doesn't line up exactly
with which events the refetch actually picked up — this EP keeps the
polled query result as the single source of truth for every KPI number,
and uses the live delta purely as a supplementary "something is
happening" indicator (Overview's delta strip). The debounced query
invalidation (1.5s, see [Performance Guide](./07-performance-guide.md))
means the authoritative number catches up within about two seconds of
the live acknowledgment appearing — correctness over the appearance of
zero latency.

## Read/dismiss state — `useNotificationStore`

Unchanged in shape from before this EP (`readIds`), extended with
`dismissedIds`/`dismiss`/`clearAll`. Both live-sourced and
client-derived alerts share this one store, keyed by each alert's own
`id` (a live event's `event_id` for real-time alerts,
`"budget-over:<project_id>"`-style deterministic ids for derived ones —
see `hooks/useAlerts.ts`). There is deliberately no second, competing
"unread count" mechanism in `useRealtimeStore` — read/unread is always
computed the same way, from this one store, regardless of an alert's
source.

## React Query — untouched cache, realtime-aware options

No new cache, no new client. `hooks/useDashboard.ts`'s existing hooks
gained two things:
1. `refetchInterval: useRealtimeRefetchInterval(60_000)` — polling only
   while the socket isn't healthy.
2. Nothing else — the query keys, `queryFn`s, and `staleTime`s are
   unchanged. `useRealtimeQueryBridge()` (mounted once) invalidates by
   key prefix from outside these hooks entirely.

See [Performance Guide](./07-performance-guide.md) for why invalidation
is debounced and [Architecture](./01-architecture.md) for the full data
flow diagram.
