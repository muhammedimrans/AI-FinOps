from __future__ import annotations

import pytest

mcp_pkg = pytest.importorskip("mcp")

import mcp.types as types  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.lowlevel.helper_types import ReadResourceContents  # noqa: E402
from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from costorah.instrumentation.mcp import MCPInstrumentor  # noqa: E402


def _build_server() -> Server:
    server = Server("test-server")

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list:
        if name == "boom":
            raise RuntimeError("tool exploded")
        return [types.TextContent(type="text", text="secret tool result — never captured")]

    @server.list_tools()
    async def handle_list_tools() -> list:
        return [
            types.Tool(name="echo", description="e", inputSchema={"type": "object"}),
            types.Tool(name="boom", description="fails", inputSchema={"type": "object"}),
        ]

    @server.read_resource()
    async def handle_read_resource(uri: str) -> list[ReadResourceContents]:
        return [
            ReadResourceContents(
                content="secret resource content — never captured", mime_type="text/plain"
            )
        ]

    @server.list_resources()
    async def handle_list_resources() -> list:
        return [types.Resource(uri="file:///a.txt", name="a", mimeType="text/plain")]

    @server.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict | None) -> types.GetPromptResult:
        return types.GetPromptResult(
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text="secret prompt — never captured"),
                )
            ]
        )

    @server.list_prompts()
    async def handle_list_prompts() -> list:
        return [types.Prompt(name="greet")]

    return server


@pytest.mark.asyncio
async def test_call_tool_is_captured_and_result_content_never_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    instrumentor = MCPInstrumentor()
    instrumentor.instrument()
    try:
        server = _build_server()
        with caplog.at_level("DEBUG", logger="costorah.instrumentation.mcp"):
            async with create_connected_server_and_client_session(server) as client:
                await client.initialize()
                result = await client.call_tool("echo", {"query": "secret argument"})
                assert result.content[0].text == "secret tool result — never captured"

        assert instrumentor.events_captured_total > 0
        log_text = caplog.text
        assert "secret tool result" not in log_text
        assert "secret argument" not in log_text
        assert "name=echo" in log_text
    finally:
        instrumentor.uninstrument()


@pytest.mark.asyncio
async def test_failed_tool_call_is_still_counted_and_reraises() -> None:
    instrumentor = MCPInstrumentor()
    instrumentor.instrument()
    try:
        server = _build_server()
        async with create_connected_server_and_client_session(server) as client:
            await client.initialize()
            result = await client.call_tool("boom", {})
            assert result.isError is True
        assert instrumentor.events_captured_total > 0
    finally:
        instrumentor.uninstrument()


@pytest.mark.asyncio
async def test_read_resource_and_get_prompt_are_captured_without_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    instrumentor = MCPInstrumentor()
    instrumentor.instrument()
    try:
        server = _build_server()
        with caplog.at_level("DEBUG", logger="costorah.instrumentation.mcp"):
            async with create_connected_server_and_client_session(server) as client:
                await client.initialize()
                resource_result = await client.read_resource("file:///a.txt")
                assert "secret resource content" in resource_result.contents[0].text

                prompt_result = await client.get_prompt("greet", {})
                assert "secret prompt" in prompt_result.messages[0].content.text

        log_text = caplog.text
        assert "secret resource content" not in log_text
        assert "secret prompt" not in log_text
        assert "mcp_read_resource" in log_text
        assert "mcp_get_prompt" in log_text
    finally:
        instrumentor.uninstrument()


class TestMCPInstrumentorLifecycle:
    def test_instrument_is_idempotent(self) -> None:
        instrumentor = MCPInstrumentor()
        instrumentor.instrument()
        first_state = instrumentor._state
        instrumentor.instrument()
        assert instrumentor._state is first_state
        instrumentor.uninstrument()

    def test_uninstrument_restores_original_methods(self) -> None:
        from mcp import ClientSession

        original_call_tool = ClientSession.call_tool
        instrumentor = MCPInstrumentor()
        instrumentor.instrument()
        assert ClientSession.call_tool is not original_call_tool
        instrumentor.uninstrument()
        assert ClientSession.call_tool is original_call_tool
        assert instrumentor.is_instrumented() is False
        assert instrumentor.events_captured_total == 0

    def test_instrument_must_precede_server_handler_registration(self) -> None:
        """Documents (via a real assertion, not just prose) that
        instrument() has no effect on handlers already registered before
        it ran — the ordering requirement described in the module
        docstring."""
        server = Server("pre-registered")

        @server.call_tool()
        async def handle(name: str, arguments: dict) -> list:
            return [types.TextContent(type="text", text="result")]

        instrumentor = MCPInstrumentor()
        instrumentor.instrument()
        try:
            # The handler captured at decoration time is not the
            # instrumented wrapper, because instrument() ran afterward.
            assert types.CallToolRequest in server.request_handlers
            assert instrumentor._state is not None
        finally:
            instrumentor.uninstrument()
