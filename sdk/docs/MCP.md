# Model Context Protocol — client and server (Python)

```python
from mcp.server.lowlevel import Server
from costorah.instrumentation.mcp import MCPInstrumentor

instrumentor = MCPInstrumentor()
instrumentor.instrument()   # must run before @server.call_tool() etc.
                             # are applied — see "Ordering" below

server = Server("my-server")

@server.call_tool()
async def handle_call_tool(name, arguments):
    ...
```

## How it works

`MCPInstrumentor` patches `mcp.ClientSession`'s `call_tool`/
`read_resource`/`get_prompt`/`list_tools`/`list_resources`/`list_prompts`
methods (timing + success/failure wrappers), and `mcp.server.lowlevel.
Server`'s `call_tool()`/`read_resource()`/`get_prompt()` decorator
factories (so whatever handler function gets registered through them is
timed the same way, without altering its return value or error behavior).

## Why this instrumentor never submits a usage event

MCP tool calls, resource reads, and prompt fetches are not LLM calls —
they carry no token counts, no cost, no LLM provider. Inventing a fake
`"mcp"` provider or a zero-cost usage record to force them into COSTORAH's
provider/model/token-shaped ingestion schema would misrepresent real spend
data. Instead, this instrumentor captures **local telemetry only**:
`events_captured_total` (a running count) plus debug-level structured log
lines with tool/resource/prompt name, duration, and success/failure.

If an MCP tool call triggers a downstream LLM call (e.g. an MCP server
that itself calls an LLM), that call is captured by whatever provider or
AI-framework instrumentor is actually instrumenting that call site — not
by this one.

## Ordering requirement (server side)

`Server.call_tool()`/`read_resource()`/`get_prompt()` are decorator
*factories* applied at handler-registration time. `MCPInstrumentor().
instrument()` must run **before** those decorators are applied — calling
`instrument()` after a server has already registered its handlers
silently instruments nothing on the server side (verified empirically;
client-side wrapping is unaffected either way, since it patches
`ClientSession` methods directly rather than per-call registrations).

## Never captured

Tool call arguments, tool call results, resource contents, and prompt
contents/arguments are never read, logged, or transmitted — only the name
being invoked, duration, and whether it raised.

## Verified against

Real `mcp` package (v1.26), using `mcp.shared.memory.
create_connected_server_and_client_session` for an in-process real
client/server pair — both client-side (`call_tool`, `read_resource`,
`get_prompt`) and server-side (`@server.call_tool()`) wrapping confirmed
working, including the failure path (a tool that raises is still counted
and its error still propagates to the caller).
