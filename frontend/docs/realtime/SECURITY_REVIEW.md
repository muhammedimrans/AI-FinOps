# Security Review — EP-19.2 Real-Time Frontend

Frontend-side review, complementing the backend's own
`backend/docs/realtime/SECURITY_REVIEW.md` (which covers cross-tenant
isolation, JWT/API-Key validation, replay resistance, connection
exhaustion, and rate limiting at the server). This review covers what's
specific to the browser client.

## Token handling

The access token travels in the WebSocket URL's `?token=` query
parameter (`connection.ts::buildWebSocketUrl`) because browser
`WebSocket` cannot set an `Authorization` header on its handshake — this
is the same fallback the backend's `extract_token()` already implements
and documents, not a new exposure this EP introduces. Consequences,
inherited from that existing design rather than new to this EP:

- The token appears in the browser's Network panel for the WS handshake
  request, same as it already does for every `Authorization`-header REST
  call visible there.
- The token does **not** appear in browser history or get logged by a
  standard reverse proxy access log the way a query parameter on a
  navigable `GET` URL would — a WebSocket upgrade request is not a page
  navigation.
- `useAuthStore.accessToken` is already memory-only, never persisted to
  `localStorage` (see `stores/auth.ts`'s existing comment on this) — the
  real-time client reads it via `getToken()` at connect/reconnect time,
  never storing its own separate copy.

## Organization isolation, frontend side

The frontend cannot leak one organization's data into another's view
even if it tried: `RealtimeSubscriptionManager.start()` disposes the
existing connection and calls `resetForOrganizationChange()` (clearing
`recentActivity`, `lastEventByType`, `liveMetrics`) *before* opening the
new connection under the new organization id (`subscriptions.ts`). This
is verified directly in
`frontend/src/realtime/__tests__/subscriptions.test.ts::"switching organizations tears down the old connection, resets store, and opens a new one"`.
The actual isolation guarantee — that the backend will never deliver
organization B's events to a connection joined to organization A — is
enforced server-side (backend's own security review); the frontend's job
is only to not retain or display stale data across a switch, which it
does.

## No new attack surface for XSS/injection

- Every rendered field from a live event goes through React's default
  JSX escaping (`{payload.provider}`, `{payload.model}`, etc.) — no
  `dangerouslySetInnerHTML` anywhere in the real-time components
  (`ConnectionIndicator.tsx`, `LiveActivityFeed.tsx`,
  `hooks/useAlerts.ts`'s live-alert rendering path in `Header.tsx`).
- `parseRealtimeFrame` (`events.ts`) only accepts frames that parse as
  JSON and match the expected envelope shape — a malformed or
  adversarial frame (were an attacker somehow able to inject one onto
  the socket, which would require compromising the backend or performing
  a MITM against a TLS connection) is silently dropped, never `eval`'d
  or otherwise executed.

## Denial of service considerations (client side)

- **Bounded memory**: `recentActivity` is capped at `activityLimit`
  (200) via `Array.prototype.slice` on every ingest — a malicious or
  buggy publisher sending a flood of events cannot grow this array
  without bound and exhaust browser memory.
- **Debounced invalidation**: `useRealtimeQueryBridge`'s 1.5s debounce
  means a burst of events triggers one refetch, not one per event — a
  flood of legitimate-looking events can't be used to hammer the REST
  API with refetches at the browser's expense (or the backend's, as a
  side effect).
- **Reconnect backoff**: capped exponential backoff with jitter
  (`connection.ts`) means a client experiencing repeated connection
  failures backs off up to 30s between attempts rather than hammering
  the WS gateway — this also cooperates with (rather than tries to
  evade) the backend's own per-IP connection-attempt rate limiter.

## What this review does not claim

Same caveat as the backend's own security review: this is an
implementer-level review, not an independent penetration test or a
browser-security audit (e.g. no formal review of Content-Security-Policy
interaction with WebSocket connections, no fuzzing of the frame parser
beyond the unit tests in `events.test.ts`). Treat it as a baseline, not
a completed sign-off.
