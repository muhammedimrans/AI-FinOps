#!/usr/bin/env python3
"""CLI real-time listener — EP-19.1.

Prints live COSTORAH events to the terminal, one line per event. Supports
both transports so it doubles as a manual smoke-test tool for either
gateway.

Usage:
    python cli_listener.py ws  --url wss://costorah.example.com/v1/ws \\
        --token <token> --organization-id <uuid>
    python cli_listener.py sse --url https://costorah.example.com/v1/events \\
        --token <token> --organization-id <uuid>

Requires `websockets` for the `ws` subcommand and `httpx` for `sse`
(both already present in this backend's own dependency set).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _format(event: dict) -> str:
    event_type = event.get("type", "?")
    payload = event.get("payload", {})
    return f"[{event.get('timestamp', '?')}] {event_type} {json.dumps(payload)}"


async def listen_ws(url: str, token: str, organization_id: str | None) -> None:
    import websockets

    query = f"?organization_id={organization_id}" if organization_id else ""
    headers = {"Authorization": f"Bearer {token}"}
    async with websockets.connect(f"{url}{query}", additional_headers=headers) as ws:
        print(f"listening on {url} (websocket)", file=sys.stderr)
        async for raw in ws:
            message = json.loads(raw)
            if message.get("type") == "ping":
                await ws.send(json.dumps({"type": "pong"}))
                continue
            print(_format(message))


async def listen_sse(url: str, token: str, organization_id: str | None) -> None:
    import httpx

    params = {"token": token}
    if organization_id:
        params["organization_id"] = organization_id

    async with httpx.AsyncClient() as client, client.stream(
        "GET", url, params=params, headers={"Accept": "text/event-stream"}, timeout=None
    ) as response:
        response.raise_for_status()
        print(f"listening on {url} (sse)", file=sys.stderr)
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                print(_format(json.loads(line[len("data: ") :])))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transport", choices=["ws", "sse"])
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--organization-id", default=None)
    args = parser.parse_args()

    if args.transport == "ws":
        asyncio.run(listen_ws(args.url, args.token, args.organization_id))
    else:
        asyncio.run(listen_sse(args.url, args.token, args.organization_id))


if __name__ == "__main__":
    main()
