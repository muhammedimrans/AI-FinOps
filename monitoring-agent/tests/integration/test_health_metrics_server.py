from __future__ import annotations

import httpx
from aiohttp.test_utils import TestClient, TestServer

from costorah_agent.agent import Agent
from costorah_agent.collectors.registry import CollectorRegistry
from costorah_agent.config import AgentConfig
from costorah_agent.server.app import build_app
from costorah_agent.transport.http_client import HttpClient
from tests.integration.conftest import wait_until


async def _running_agent(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry, handler
) -> Agent:
    http_client = HttpClient(
        endpoint=agent_config.server.endpoint,
        api_key=agent_config.organization.api_key,
        transport=httpx.MockTransport(handler),
    )
    agent = Agent(agent_config, registry=dummy_registry, http_client=http_client)
    await agent.start()
    return agent


async def test_health_endpoint_reports_healthy_after_successful_delivery(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": False})

    agent = await _running_agent(agent_config, dummy_registry, handler)
    try:
        await wait_until(lambda: agent.sender.metrics.events_sent_total >= 1)

        app = build_app(agent)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/health")
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "healthy"
            assert body["queue_size"] == 0
            assert body["collectors"][0]["name"] == "openai"
            assert body["collectors"][0]["healthy"] is True
    finally:
        await agent.shutdown()


async def test_health_endpoint_reports_degraded_when_a_collector_is_unhealthy(
    agent_config: AgentConfig, unhealthy_dummy_registry: CollectorRegistry
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": False})

    agent = await _running_agent(agent_config, unhealthy_dummy_registry, handler)
    try:
        app = build_app(agent)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/health")
            body = await resp.json()
            assert body["status"] == "degraded"
            assert body["collectors"][0]["healthy"] is False
    finally:
        await agent.shutdown()


async def test_metrics_endpoint_exposes_prometheus_format(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": False})

    agent = await _running_agent(agent_config, dummy_registry, handler)
    try:
        await wait_until(lambda: agent.sender.metrics.events_sent_total >= 1)

        app = build_app(agent)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/metrics")
            assert resp.status == 200
            assert resp.content_type == "text/plain"
            text = await resp.text()
            assert "costorah_agent_events_sent_total 1" in text
            assert 'costorah_agent_events_by_provider_total{provider="openai"} 1' in text
            assert "costorah_agent_info" in text
    finally:
        await agent.shutdown()
