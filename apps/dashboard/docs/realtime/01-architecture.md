# Real-Time Frontend Architecture — EP-19.2

## What this EP adds

EP-19.1 built the backend's `GET /v1/ws` gateway. EP-19.2 turns the
dashboard from a polling-only client into one that consumes it, while
every existing React Query polling hook keeps working unmodified as the
fallback path:

```
Backend (EP-19.1)                Frontend (EP-19.2)
──────────────────                ──────────────────
Redis Event Bus
      │ PSUBSCRIBE
GET /v1/ws  ───────wss────────▶  RealtimeClient (src/realtime/client.ts)
                                        │ dispatch
                                  RealtimeSubscriptionManager
                                        │ (module singleton)
                          ┌─────────────┼─────────────┐
                          ▼             ▼             ▼
                   RealtimeStore   Query bridge   Component
                   (Zustand)      (invalidate)    subscribers
                          │             │             │
                          ▼             ▼             ▼
                 ConnectionIndicator  useOverview/   LiveActivityFeed,
                 LiveActivityFeed     useTimeSeries/  useAlerts (live
                 useAlerts (live)     etc. refetch    notifications)
```

## Module layout

`frontend/src/realtime/` — no business logic in components, per the
ticket's explicit instruction:

| File | Responsibility |
|---|---|
| `types.ts` | Wire types mirroring the backend's `RealtimeEvent` envelope exactly. |
| `events.ts` | Frame parsing — turns a raw WS text frame into a `RealtimeEvent` or `null`, never throws. |
| `connection.ts` | Pure helpers: WS URL construction, exponential-backoff-with-jitter delay calculation, close-code classification. No `WebSocket` dependency — trivially unit tested. |
| `heartbeat.ts` | Ping/pong bookkeeping, transport-agnostic. |
| `client.ts` | `RealtimeClient` — wraps the browser's native `WebSocket`, owns reconnect/heartbeat/parsing for one connection. |
| `store.ts` | `useRealtimeStore` (Zustand) — connection status, bounded local activity buffer, per-type last-event cache, live metrics delta. |
| `subscriptions.ts` | `RealtimeSubscriptionManager` — the one app-wide connection (module singleton), org-switch handling, per-type/wildcard listener dispatch. |
| `hooks.ts` | The React-facing API: `useRealtimeConnection`, `useConnectionStatus`, `useLiveActivity`, `useLiveMetrics`, `useRealtimeEvent`, `useRealtimeRefetchInterval`. |
| `queryBridge.ts` | `useRealtimeQueryBridge` — invalidates the affected React Query keys on `usage.created`, debounced. |

## Why a WebSocket client, not SSE, on the frontend

The backend exposes both `GET /v1/ws` and `GET /v1/events` (SSE). This EP
builds only a WebSocket client, matching the ticket's own architecture
diagram (`Backend → Redis Event Bus → WebSocket → Real-Time Store →
Dashboard`) and its explicit module list (`client.ts`, `connection.ts`,
`heartbeat.ts` — heartbeat only matters for a bidirectional transport;
SSE's keepalive is an invisible server-sent comment line the client never
acts on). One transport keeps the reconnect/heartbeat/backpressure logic
in one place instead of two parallel implementations.

**Trade-off, stated plainly**: SSE's `EventSource` gets automatic
reconnect and `Last-Event-ID` replay for free from the browser. Building
on WebSocket instead means this EP had to hand-roll reconnect (see
`connection.ts`) and does **not** get gap-filling replay after a
disconnect — a dropped WebSocket connection does not recover events
missed while offline. See
[Connection Lifecycle](./04-connection-lifecycle.md#no-gap-fill-replay-on-reconnect)
for the honest accounting of this gap and how it's mitigated (React
Query's polling fallback catches up on reconnect regardless).

## Singleton, not per-component

`realtimeSubscriptions` (in `subscriptions.ts`) and `useRealtimeStore`
are both module-level singletons, not values created per component or
per `useEffect`. There is exactly one real-time connection for the whole
app — it's joined to one organization for its entire lifetime, matching
the backend's connection model — so a singleton is the correct shape,
not a shortcut. `useRealtimeConnection()` (mounted once, in
`AppLayout.tsx`) is the only place that calls `start()`/`stop()`;
everything else only reads from the store or subscribes to events.

## No new state-management library

Real-time state lives in a Zustand store, matching every other piece of
client state in this app (`useAuthStore`, `useOrgStore`, `useUIStore`,
`useNotificationStore`, `useToastStore` all already use Zustand). No
Redux, no XState, no new dependency.
