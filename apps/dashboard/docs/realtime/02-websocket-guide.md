# WebSocket Guide (Frontend)

## Connecting

Nothing to call manually — `useRealtimeConnection()` is mounted once in
`AppLayout.tsx` and does the whole lifecycle:

```tsx
// AppLayout.tsx
useRealtimeConnection();   // watches auth + org stores, connects/reconnects/disconnects
useRealtimeQueryBridge();  // invalidates dashboard queries on usage.created
```

It reacts to:
- **Login** — `useAuthStore`'s `accessToken` becoming non-null starts the connection.
- **Logout** — `accessToken` becoming null stops it.
- **Organization switch** — `useOrgStore`'s `organizationId` changing tears
  down the old connection, clears all live state, and opens a new one
  under the new organization (see
  [Connection Lifecycle](./04-connection-lifecycle.md#organization-switching)).
- **Token refresh** — the client re-reads the token from the auth store on
  every reconnect attempt (`getToken` is a function, not a captured
  string), so a rotated token is picked up automatically; a connection
  stuck in `auth_failed` is also nudged to retry immediately once a fresh
  token appears.

## Authentication — reused, not reinvented

Browser `WebSocket` cannot set an `Authorization` header on its handshake
request, so `buildWebSocketUrl()` (`connection.ts`) puts the token in
`?token=`, exactly the fallback the backend's
`app/realtime/auth.py::extract_token()` already implements for browser
clients. No new token type, no new login flow — the same JWT access
token every REST call already uses.

## Reading events in a component

```tsx
import { useRealtimeEvent } from "../realtime/hooks";

function MyWidget() {
  useRealtimeEvent("usage.created", (event) => {
    console.log(event.payload); // { provider, model, cost, ... }
  });
  // ...
}
```

`useRealtimeEvent("*", handler)` subscribes to every event type instead
of one. The subscription is automatically cleaned up when the component
unmounts — no manual `off()` call needed.

## Reading connection status

```tsx
import { useConnectionStatus } from "../realtime/hooks";

function StatusText() {
  const connection = useConnectionStatus();
  return <span>{connection.status}</span>; // "connected" | "connecting" | ...
}
```

See [Connection Lifecycle](./04-connection-lifecycle.md) for the full
state list and what each one means.

## What a raw frame looks like

Identical to the backend's `RealtimeEvent` envelope
(`backend/docs/realtime/04-event-model.md`) — `types.ts` mirrors it
field-for-field:

```json
{
  "event_id": "0d3f2b1e-...",
  "timestamp": "2026-07-03T12:00:00Z",
  "organization_id": "b2a1c3d4-...",
  "type": "usage.created",
  "version": 1,
  "payload": { "provider": "openai", "model": "gpt-4.1", "cost": "0.0812", "currency": "USD", "total_tokens": 1520, "status": "success", "project_id": null },
  "trace_id": "req_abc123",
  "correlation_id": null
}
```

A server heartbeat frame (`{"type":"ping"}`) is handled entirely inside
`client.ts` — it never reaches `useRealtimeEvent` subscribers; there is
no `"ping"` event type to subscribe to.
