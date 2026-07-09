# Connection Lifecycle

## States

`ConnectionStatus` (`types.ts`), matching the ticket's named states
exactly:

| State | Meaning | User-visible |
|---|---|---|
| `connecting` | First connection attempt in progress. | "Connecting" pill |
| `connected` | Socket open, heartbeats healthy. | "Live" pill (green, pulsing dot) |
| `reconnecting` | A previous connection dropped; backoff timer running before the next attempt. | "Reconnecting" pill (amber, spinning icon) |
| `offline` | Closed with a non-retryable code that isn't an auth failure (currently unused by the backend, reserved). | "Offline" pill |
| `auth_failed` | Token missing/invalid/expired, or the backend rejected the connection (close code 4401). | "Sign-in required" pill (red) |
| `organization_changed` | Transient — set for one tick while switching organizations, before the new connection's `connecting` status lands. | Not shown long enough to matter visually |

## Connect → authenticate → join → heartbeat → receive

1. `useRealtimeConnection()` sees a token and organization id, calls
   `realtimeSubscriptions.start(getToken, organizationId)`.
2. `RealtimeClient.connect()` builds the WS URL
   (`?organization_id=...&token=...`) and opens the socket.
3. The backend authenticates and joins the connection to that
   organization's event stream (all server-side, see the backend's
   [Authentication doc](../../backend/docs/realtime/05-authentication.md)) —
   nothing further needed on the frontend.
4. Every 30s the server sends `{"type":"ping"}`; `client.ts` replies
   `{"type":"pong"}` immediately (see `heartbeat.ts`).
5. `RealtimeEvent` frames arrive as JSON text frames, parsed by
   `events.ts`, dispatched to the store and any `useRealtimeEvent`
   subscribers.

## Reconnecting

`connection.ts::reconnectDelayMs(attempt)` — exponential backoff (1s
base, doubling, capped at 30s) with ±20% jitter so a fleet of clients
reconnecting after a shared outage doesn't retry in lockstep. The close
code decides whether to retry at all:

- **4401 (auth failed)** → `auth_failed`, no automatic retry. Retrying
  with the same bad token would just fail again; the connection is
  nudged to retry immediately once `useRealtimeConnection` sees a fresh
  token (e.g. after a refresh completes).
- **4429 (rate limited)**, **4408 (heartbeat timeout)**, any other close
  → `reconnecting`, backoff, retry.

## Organization switching

Handled entirely by `RealtimeSubscriptionManager.start()`
(`subscriptions.ts`) when called with a new organization id:

1. The old `RealtimeClient` is disposed (socket closed with code 1000).
2. `useRealtimeStore.resetForOrganizationChange()` clears
   `recentActivity`, `lastEventByType`, and `liveMetrics` — this is what
   guarantees no stray render can show one organization's live numbers
   under another organization's context.
3. A new `RealtimeClient` is created and connected under the new
   organization id.

Verified directly in
`frontend/src/realtime/__tests__/subscriptions.test.ts`.

## No gap-fill replay on reconnect

This is the one honest limitation carried over from the backend's own
docs (`backend/docs/realtime/02-websocket-guide.md`): a WebSocket that
drops mid-session and reconnects does **not** receive events published
while it was offline. The backend's SSE endpoint supports
`Last-Event-ID` gap-fill replay; this frontend's WebSocket client does
not use SSE, so it doesn't get that for free, and nothing in this EP
implements an equivalent for WebSocket (the backend has no per-connection
resume-from-id protocol for WS — see EP-19.1's own docs on this
asymmetry).

**Why this is an acceptable trade-off in practice**: the React Query
bridge's polling fallback (`useRealtimeRefetchInterval`) kicks in the
moment the connection isn't `connected`, and the moment a reconnect
succeeds, the query bridge's normal debounced invalidation resumes —
so the dashboard's numbers catch up via a poll shortly after
reconnecting, even though the live event *stream* itself has a gap. The
`recentActivity` local buffer (`useRealtimeStore`) will show a visible
gap in the activity feed's timeline for whatever was missed, which is
honest rather than papered over with fabricated data.
