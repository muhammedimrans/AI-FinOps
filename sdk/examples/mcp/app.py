"""MCP + COSTORAH example (EP-18.7).

Demonstrates MCPInstrumentor().instrument() capturing tool-call telemetry
for both an MCP server and its client, in a single in-process pair (using
mcp.shared.memory, the same helper the SDK's own tests use) — zero manual
tracking calls, and never capturing tool arguments/results.

Note: instrument() must run before @server.call_tool() etc. are applied —
see sdk/docs/MCP.md's "Ordering requirement".
"""

from __future__ import annotations

import asyncio
import logging

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_connected_server_and_client_session

from costorah.instrumentation.mcp import MCPInstrumentor

logging.basicConfig(level=logging.DEBUG)

instrumentor = MCPInstrumentor()
instrumentor.instrument()

server = Server("costorah-example-server")


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list:
    if name == "add":
        result = arguments["a"] + arguments["b"]
        return [types.TextContent(type="text", text=str(result))]
    raise ValueError(f"Unknown tool: {name}")


@server.list_tools()
async def handle_list_tools() -> list:
    return [
        types.Tool(
            name="add",
            description="Add two numbers",
            inputSchema={
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
        )
    ]


async def main() -> None:
    async with create_connected_server_and_client_session(server) as client:
        await client.initialize()
        result = await client.call_tool("add", {"a": 2, "b": 3})
        print("Tool result:", result.content[0].text)
    print(f"Events captured by MCPInstrumentor: {instrumentor.events_captured_total}")


if __name__ == "__main__":
    asyncio.run(main())
