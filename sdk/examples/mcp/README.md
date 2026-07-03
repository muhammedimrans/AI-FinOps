# MCP + COSTORAH example

A minimal in-process MCP server + client pair demonstrating
`MCPInstrumentor().instrument()` capturing tool-call telemetry on both
sides, with no manual tracking calls and no COSTORAH API key required (this
example never submits a usage event — see "Why no usage event" below).

## Setup

```bash
cd sdk/examples/mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python3 app.py
```

## Expected output

Debug logs from both the MCP SDK and `costorah.instrumentation.mcp`
showing `mcp_server_call_tool name=add duration_ms=... success=True` and
`mcp_call_tool name=add duration_ms=... success=True`, followed by the
tool result (`5`) and a final events-captured count.

## Why no usage event

MCP tool calls aren't LLM calls — they have no tokens, no cost, no LLM
provider. `MCPInstrumentor` captures local telemetry only
(`events_captured_total`, structured debug logs); it never submits a
usage record to COSTORAH. See `sdk/docs/MCP.md`.
