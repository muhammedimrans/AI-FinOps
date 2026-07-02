from __future__ import annotations

import httpx

from costorah_agent.agent import Agent
from costorah_agent.collectors.registry import CollectorRegistry
from costorah_agent.config import AgentConfig
from costorah_agent.transport.http_client import HttpClient
from tests.integration.conftest import wait_until


async def test_offline_mode_persists_events_instead_of_losing_them(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry
) -> None:
    """COSTORAH is unreachable (503) for the entire test — the event must
    end up durably persisted in SQLite, never silently dropped."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "service unavailable"})

    http_client = HttpClient(
        endpoint=agent_config.server.endpoint,
        api_key=agent_config.organization.api_key,
        transport=httpx.MockTransport(handler),
    )
    agent = Agent(agent_config, registry=dummy_registry, http_client=http_client)
    await agent.start()
    try:
        await wait_until(lambda: agent.sender.metrics.retries_total >= 1)
    finally:
        await agent.shutdown()

    assert agent.sender.metrics.events_sent_total == 0
    assert await agent.store.count() == 1  # never lost, just waiting to retry


async def test_reconnect_drains_queued_events_after_recovery(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry
) -> None:
    """Backend is down initially, then recovers — the previously-persisted
    event must be delivered once the backend is reachable again, with no
    manual intervention (this is what the retry loop is for)."""
    state = {"available": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if not state["available"]:
            return httpx.Response(503, json={"detail": "service unavailable"})
        return httpx.Response(200, json={"success": True, "usage_id": "u1", "duplicate": False})

    http_client = HttpClient(
        endpoint=agent_config.server.endpoint,
        api_key=agent_config.organization.api_key,
        transport=httpx.MockTransport(handler),
    )
    agent = Agent(agent_config, registry=dummy_registry, http_client=http_client)
    await agent.start()
    try:
        # First: confirm the event is stuck in the durable store while down.
        await wait_until(lambda: agent.sender.metrics.retries_total >= 1)
        assert await agent.store.count() == 1
        assert agent.sender.metrics.events_sent_total == 0

        # Backend comes back — the agent's own retry loop should notice on
        # its next due-retry pass (backoff is 0.05s in agent_config) and
        # drain the store without any external trigger.
        state["available"] = True
        await wait_until(lambda: agent.sender.metrics.events_sent_total >= 1, timeout=3.0)
    finally:
        await agent.shutdown()

    assert agent.sender.metrics.events_sent_total == 1
    assert await agent.store.count() == 0


async def test_validation_error_is_not_endlessly_retried(
    agent_config: AgentConfig, dummy_registry: CollectorRegistry
) -> None:
    """A permanently-malformed payload (400/404/422) must be dropped, not
    retried forever — distinct from the offline/503 case above."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "invalid provider"})

    http_client = HttpClient(
        endpoint=agent_config.server.endpoint,
        api_key=agent_config.organization.api_key,
        transport=httpx.MockTransport(handler),
    )
    agent = Agent(agent_config, registry=dummy_registry, http_client=http_client)
    await agent.start()
    try:
        await wait_until(lambda: agent.sender.metrics.events_failed_total >= 1)
    finally:
        await agent.shutdown()

    assert agent.sender.metrics.events_failed_total == 1
    assert await agent.store.count() == 0  # dropped, not persisted for retry
