from __future__ import annotations

import asyncio

import httpx

from costorah_agent.agent import Agent
from costorah_agent.collectors.registry import CollectorRegistry
from costorah_agent.config import AgentConfig
from costorah_agent.transport.http_client import HttpClient
from tests.integration.conftest import wait_until


async def test_usage_upload_end_to_end(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry
) -> None:
    """Collector -> queue -> sender -> HTTP client -> mocked ingestion API,
    driven entirely through the real Agent orchestration loops."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": False})

    http_client = HttpClient(
        endpoint=agent_config.server.endpoint,
        api_key=agent_config.organization.api_key,
        transport=httpx.MockTransport(handler),
    )
    agent = Agent(agent_config, registry=dummy_registry, http_client=http_client)
    await agent.start()
    try:
        await wait_until(lambda: agent.sender.metrics.events_sent_total >= 1)
    finally:
        await agent.shutdown()

    assert agent.sender.metrics.events_sent_total == 1
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/ingest/usage"
    body = requests[0].content.decode()
    assert '"provider":"openai"' in body or '"provider": "openai"' in body


async def test_authentication_header_uses_bearer_costorah_key(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry
) -> None:
    seen_auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth_headers.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": False})

    http_client = HttpClient(
        endpoint=agent_config.server.endpoint,
        api_key=agent_config.organization.api_key,
        transport=httpx.MockTransport(handler),
    )
    agent = Agent(agent_config, registry=dummy_registry, http_client=http_client)
    await agent.start()
    try:
        await wait_until(lambda: len(seen_auth_headers) >= 1)
    finally:
        await agent.shutdown()

    assert seen_auth_headers
    assert seen_auth_headers[0] == f"Bearer {agent_config.organization.api_key}"
    assert seen_auth_headers[0].startswith("Bearer costorah_live_")


async def test_health_reflects_unhealthy_collector(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": False})

    http_client = HttpClient(
        endpoint=agent_config.server.endpoint,
        api_key=agent_config.organization.api_key,
        transport=httpx.MockTransport(handler),
    )
    agent = Agent(agent_config, registry=dummy_registry, http_client=http_client)
    await agent.start()
    try:
        await asyncio.sleep(0.1)
        health = await agent.collector_health()
    finally:
        await agent.shutdown()

    assert len(health) == 1
    assert health[0].name == "openai"
    assert health[0].healthy is True
