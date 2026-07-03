#!/usr/bin/env python3
"""Python WebSocket example client — EP-19.1.

Connects to COSTORAH's real-time gateway, authenticates with a JWT or
Organization API Key, and prints every event as it arrives. Replies to
the server's heartbeat ping so the connection isn't closed as stale.

Usage:
    python python_ws_client.py \\
        --url wss://costorah.example.com/v1/ws \\
        --token <jwt-or-api-key> \\
        --organization-id <uuid>   # required for a JWT, optional for an API Key

Requires the `websockets` package (already a transitive dependency of
this backend's own `fastapi[standard]`/`uvicorn[standard]`, or install
directly: `pip install websockets`).
"""

from __future__ import annotations

import argparse
import asyncio
import json

import websockets


async def listen(url: str, token: str, organization_id: str | None) -> None:
    query = f"?organization_id={organization_id}" if organization_id else ""
    full_url = f"{url}{query}"
    headers = {"Authorization": f"Bearer {token}"}

    async with websockets.connect(full_url, additional_headers=headers) as ws:
        print(f"connected to {full_url}")
        async for raw in ws:
            try:
                message = json.loads(raw)
            except ValueError:
                print(f"non-JSON frame: {raw!r}")
                continue

            if message.get("type") == "ping":
                await ws.send(json.dumps({"type": "pong"}))
                continue

            print(json.dumps(message, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="wss://costorah.example.com/v1/ws")
    parser.add_argument("--token", required=True, help="JWT access token or Organization API Key")
    parser.add_argument("--organization-id", default=None)
    args = parser.parse_args()

    asyncio.run(listen(args.url, args.token, args.organization_id))


if __name__ == "__main__":
    main()
