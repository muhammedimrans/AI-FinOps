# Server-Sent Events Guide — `GET /v1/events`

SSE is the better fit for read-only dashboard clients: it works over
plain HTTP (no separate protocol upgrade), reconnects automatically in
every browser's native `EventSource`, and — unlike this EP's WebSocket
gateway — supports catching up on events missed while disconnected via
`Last-Event-ID`.

## Connecting

```
GET /v1/events?organization_id=<uuid>&token=<jwt-or-api-key>
Accept: text/event-stream
```

Or with a header instead of `?token=`:

```
GET /v1/events?organization_id=<uuid>
Authorization: Bearer <jwt-or-api-key>
```

Same auth rules as the WebSocket gateway — see
[Authentication](./05-authentication.md). Browser `EventSource` cannot
set custom headers, so browser clients must use `?token=`.

## Response format

Standard `text/event-stream`. Each event:

```
id: <event_id>
event: usage.created
data: {"event_id": "...", "organization_id": "...", "type": "usage.created", ...}

```

`id` is the event's `event_id` (a UUID) — `EventSource` tracks this
automatically and sends it back as `Last-Event-ID` on reconnect. `event`
is the `RealtimeEvent.type` value, so clients can use
`addEventListener("usage.created", ...)` instead of a single generic
`onmessage` handler if they want per-type routing.

Every 30 seconds with no event to send, the server writes a comment line
(`: heartbeat\n\n`) to keep the connection alive through proxies that
would otherwise time out an idle HTTP response. Comment lines are
invisible to `EventSource` — they never fire `onmessage`.

## JavaScript (browser) example

```js
const events = new EventSource(
  `/v1/events?organization_id=${orgId}&token=${token}`
);
events.onmessage = (event) => {
  console.log(JSON.parse(event.data));
};
events.addEventListener("usage.created", (event) => {
  console.log("new usage:", JSON.parse(event.data));
});
```

Runnable version: [`examples/realtime/js_ws_client.html`](../../examples/realtime/js_ws_client.html)
(includes both the WebSocket and SSE variants).

## Reconnecting with `Last-Event-ID`

`EventSource` reconnects automatically on any connection drop and sends
the last event's id back as a `Last-Event-ID` request header. The server
looks that id up in the organization's replay buffer
(`EventBus.replay_since`, a Redis list capped at 200 entries / 1 hour) and
replays everything published after it, before resuming the live stream.
If the id is unknown (the buffer rotated past it, or the server
restarted), everything currently buffered is replayed instead of nothing
— see `EventBus.replay_since`'s docstring in
`app/realtime/event_bus.py` for the exact fallback rules.

This is the one place EP-19.1 offers at-least-once-within-an-hour
delivery; live dispatch (the common case) is best-effort and can drop
events under backpressure — see [Scaling](./06-scaling.md).

## Python example

```python
import httpx

with httpx.stream(
    "GET",
    "https://costorah.example.com/v1/events",
    params={"organization_id": org_id, "token": token},
    headers={"Accept": "text/event-stream"},
) as response:
    for line in response.iter_lines():
        if line.startswith("data: "):
            print(line[len("data: "):])
```

Runnable version: [`examples/realtime/cli_listener.py`](../../examples/realtime/cli_listener.py)
supports both WebSocket and SSE.
