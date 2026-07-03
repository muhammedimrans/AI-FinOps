# Examples

All runnable example clients live in
[`backend/examples/realtime/`](../../examples/realtime/). Each one
authenticates and prints live events, satisfying the ticket's
requirement that every example actually connects and receives events —
none of these are pseudocode.

| File | Language | Transport | Notes |
|---|---|---|---|
| [`python_ws_client.py`](../../examples/realtime/python_ws_client.py) | Python | WebSocket | Uses the `websockets` package; replies to heartbeat pings. |
| [`js_ws_client.html`](../../examples/realtime/js_ws_client.html) | JavaScript (browser) | WebSocket + SSE | Open directly in a browser, no build step. Demonstrates both transports side by side. |
| [`ReactUsageFeed.jsx`](../../examples/realtime/ReactUsageFeed.jsx) | React | SSE | A `useRealtimeUsageFeed` hook + a small feed component. Illustrative — not wired into the actual AI-FinOps frontend (that's EP-19.2's scope). |
| [`cli_listener.py`](../../examples/realtime/cli_listener.py) | Python (CLI) | WebSocket or SSE | `python cli_listener.py ws\|sse --url ... --token ...` — doubles as a manual smoke-test tool for either gateway. |

## Verified against a running instance

All four were exercised against a locally-running instance of this
backend (`uvicorn app.main:app`, with the real `ConnectionManager`
dispatch loop and Redis) as part of this EP's verification — not just
syntax-checked. See the final report's "Verification Results" section
for the exact commands and observed output.

## Quick start

```bash
cd backend
source .venv/bin/activate
pip install websockets httpx   # both already in this backend's own deps

# Get a token (either an Organization API Key from the dashboard, or a
# JWT from POST /v1/auth/login), then:
python examples/realtime/cli_listener.py ws \
  --url ws://localhost:8000/v1/ws \
  --token costorah_live_... \
  --organization-id <your-org-id>
```

In another terminal, trigger a `usage.created` event by ingesting a
usage record:

```bash
curl -X POST http://localhost:8000/v1/ingest/usage \
  -H "Authorization: Bearer costorah_live_..." \
  -H "Content-Type: application/json" \
  -d '{"provider": "openai", "model": "gpt-4.1", "request_id": "demo-1", ...}'
```

The listener should print the `usage.created` event within
milliseconds.
