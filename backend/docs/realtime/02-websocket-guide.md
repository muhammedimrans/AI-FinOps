# WebSocket Guide — `GET /v1/ws`

## Connecting

```
wss://<host>/v1/ws?organization_id=<uuid>&token=<jwt-or-api-key>
```

Or, for clients that can set custom headers on the handshake:

```
wss://<host>/v1/ws?organization_id=<uuid>
Authorization: Bearer <jwt-or-api-key>
```

`Authorization` header wins if both are present. Browser `WebSocket`
cannot set custom headers on the handshake request, so browser clients
must use `?token=`.

`organization_id` is required when authenticating with a JWT (a user can
belong to more than one organization — the connection must say which
one it's joining). It is optional for an API Key, since a key belongs to
exactly one organization; if supplied, it must match the key's
organization or the connection is rejected
(`organization_mismatch`).

## Connection flow

1. Client opens the WebSocket.
2. Server **accepts the WebSocket first** (EP-24.6.1) — this is required
   for any subsequent `close(code=...)` to actually reach the client as
   that numeric code. Per the ASGI spec, a server that sends
   `websocket.close` as its first message (before `websocket.accept`)
   never completes the opening HTTP Upgrade handshake — the client never
   sees a custom close code, only a generic `1006` (abnormal closure), the
   browser's own catch-all for "the handshake never properly finished."
   Pre-EP-24.6.1, this doc described the rate-limit/auth checks as
   happening *before* accept, which was itself the bug: every rejection
   silently downgraded to an undiagnosable `1006` in real browsers.
3. Server checks the per-IP rate limit
   (`app.realtime.rate_limit.ConnectionRateLimiter`, 30 attempts/min by
   default) — over the limit closes with code `4429`.
4. Server authenticates via
   `app.realtime.auth.authenticate_realtime_connection()` — on failure,
   closes with code `4401` and a reason string.
5. Server registers the connection with the `ConnectionManager`, joining
   that organization's event stream.
6. Server sends a `{"type": "ping"}` heartbeat every 30 seconds and
   expects any client frame back within 10 seconds
   (see [Heartbeat](#heartbeat)).
7. Events for that organization are pushed as JSON text frames, one
   `RealtimeEvent` per frame (see [Event Model](./04-event-model.md)).
8. **The server always sends an explicit `close` frame before the
   connection ends** (EP-19.4) — regardless of *why* it ends (heartbeat
   timeout, the client disconnecting, or an internal error). This closes
   a second class of `1006` bug distinct from the accept-ordering one
   above: per uvicorn's own ASGI runner, a WebSocket handler that returns
   without ever having sent a `"websocket.close"` message causes uvicorn
   to fall back to a raw TCP close with no WebSocket closing handshake —
   which a browser also reports as `CloseEvent{code: 1006}`, this time
   with no code or reason at all. A single lock now serializes every
   outbound frame (ping, forwarded event, close) across the connection's
   two internal tasks, and the connection handler's cleanup path always
   attempts a close — `1011`/"Internal error" for an unexpected failure,
   `1000` otherwise — before returning. See the comment above `write_lock`
   in `app/api/v1/realtime.py` for the full root-cause writeup.

## Python example

```python
import asyncio
import websockets

async def main():
    url = "wss://costorah.example.com/v1/ws?organization_id=<org-id>"
    headers = {"Authorization": "Bearer <token>"}
    async with websockets.connect(url, additional_headers=headers) as ws:
        async for message in ws:
            print(message)

asyncio.run(main())
```

> The `websockets` library renamed its header-injection keyword from
> `extra_headers` to `additional_headers` in v14. This backend's own
> environment has `websockets` 16.0 installed (a transitive dependency of
> `fastapi[standard]`/`uvicorn[standard]`), so the example above and
> [`examples/realtime/python_ws_client.py`](../../examples/realtime/python_ws_client.py)
> use `additional_headers`. If you're on an older `websockets` (<14),
> use `extra_headers` instead — the rest of the API is unchanged.

Runnable version: [`examples/realtime/python_ws_client.py`](../../examples/realtime/python_ws_client.py).

## JavaScript (browser) example

```js
const ws = new WebSocket(
  `wss://costorah.example.com/v1/ws?organization_id=${orgId}&token=${token}`
);
ws.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  console.log(payload);
};
ws.onopen = () => console.log("connected");
ws.onclose = (e) => console.log("closed", e.code, e.reason);
```

Runnable version: [`examples/realtime/js_ws_client.html`](../../examples/realtime/js_ws_client.html).

## Heartbeat

Every 30 seconds the server sends `{"type": "ping"}`. Any frame sent back
by the client within 10 seconds counts as a healthy reply — this EP does
not require a specific `{"type": "pong"}` shape, since browser
`WebSocket` clients that just read events and never write anything would
otherwise be closed as unhealthy. If a client wants to be a well-behaved
peer, replying `{"type": "pong"}` is the convention the example clients
use. Missing the 10-second window closes the connection with code `4408`
and increments both that connection's `heartbeat_failures` counter and
the `aifinops_realtime_heartbeat_failures_total` Prometheus counter.

## Close codes

| Code | Meaning |
|---|---|
| `4429` | Rate limited — too many connection attempts from this IP |
| `4401` | Authentication failed (invalid/expired token, insufficient permission, wrong organization, etc.) |
| `4408` | Heartbeat timeout — no client frame within 10s of a ping |
| `1000` | Normal closure (client disconnected, or the server ended the connection with nothing else to report) |
| `1011` | Internal error — an unexpected exception on the server side (EP-19.4); still an explicit close, never a silent `1006` |

## Reconnecting

There is no server-side session to resume on a WebSocket reconnect —
simply open a new connection. Pass `?reconnect=1` so the server records
the attempt in `aifinops_realtime_reconnects_total{kind="websocket"}` and
the new connection's `reconnect_count` field; it has no effect on
behavior otherwise. Events published while disconnected are not
delivered over WebSocket — a client that needs to catch up on missed
events should use [SSE's `Last-Event-ID` replay](./03-sse-guide.md#reconnecting-with-last-event-id)
instead, or fall back to the existing polling APIs.
