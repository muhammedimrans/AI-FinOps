"""
Local health/metrics HTTP server — localhost:9091 by default.

Binds to 127.0.0.1 (not 0.0.0.0) unless explicitly configured otherwise:
these endpoints expose operational metadata (queue depth, error rates)
about a process holding a live API key, so they should not be reachable
off-host by default.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from costorah_agent.server.metrics import MetricsSnapshot, render_prometheus
from costorah_agent.version import __version__

if TYPE_CHECKING:
    from costorah_agent.agent import Agent


def build_app(agent: Agent) -> web.Application:
    app = web.Application()
    app["agent"] = agent
    app.router.add_get("/health", _health_handler)
    app.router.add_get("/metrics", _metrics_handler)
    return app


async def _health_handler(request: web.Request) -> web.Response:
    agent: Agent = request.app["agent"]
    sender = agent.sender
    collector_health = await agent.collector_health()
    all_configured_collectors_healthy = (
        all(h.healthy for h in collector_health) if collector_health else True
    )

    status = "healthy"
    if agent.queue_size > 0 and sender.metrics.uploads_total == 0:
        status = "degraded"  # never successfully delivered anything yet
    if not all_configured_collectors_healthy:
        status = "degraded"

    body = {
        "status": status,
        "queue_size": agent.queue_size,
        "offline_store_size": await agent.store.count(),
        "last_upload": (
            sender.metrics.last_upload_at.isoformat() if sender.metrics.last_upload_at else None
        ),
        "version": __version__,
        "started_at": agent.started_at.isoformat() if agent.started_at else None,
        "collectors": [h.to_dict() for h in collector_health],
    }
    return web.json_response(body)


async def _metrics_handler(request: web.Request) -> web.Response:
    agent: Agent = request.app["agent"]
    snapshot = MetricsSnapshot(
        queue_size=agent.queue_size,
        store_size=await agent.store.count(),
        sender=agent.sender.metrics,
        version=__version__,
    )
    text = render_prometheus(snapshot)
    return web.Response(text=text, content_type="text/plain")


async def run_server(agent: Agent, *, host: str, port: int) -> web.AppRunner:
    """Start the health/metrics server and return its runner (caller owns
    shutdown via `await runner.cleanup()`)."""
    app = build_app(agent)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
