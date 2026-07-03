"""Real Prometheus instrumentation for the real-time platform — EP-19.1.

The backend's existing `GET /metrics` (`app/api/v1/health.py`) returns a
hand-written, static text block — no real `prometheus_client` counters
back it (see `docs/backend/REALTIME_ARCHITECTURE.md`'s Monitoring section
for that gap, called out honestly rather than papered over). This module
adds `prometheus_client` as a genuine, new dependency and wires real
metrics for exactly the six series the ticket names; `health.py` appends
`generate_latest()`'s output after its existing static text rather than
replacing it, so no previously-shipped EP's endpoint output is rewritten.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

realtime_registry = CollectorRegistry()

active_connections = Gauge(
    "aifinops_realtime_active_connections",
    "Currently open real-time connections",
    ["kind"],  # "websocket" | "sse"
    registry=realtime_registry,
)

events_dispatched_total = Counter(
    "aifinops_realtime_events_dispatched_total",
    "Events successfully queued for delivery to a connection",
    registry=realtime_registry,
)

events_dropped_total = Counter(
    "aifinops_realtime_events_dropped_total",
    "Events dropped because a connection's queue was full (backpressure)",
    registry=realtime_registry,
)

reconnects_total = Counter(
    "aifinops_realtime_reconnects_total",
    "Client reconnect attempts (WebSocket re-connect or SSE Last-Event-ID resume)",
    ["kind"],
    registry=realtime_registry,
)

heartbeat_failures_total = Counter(
    "aifinops_realtime_heartbeat_failures_total",
    "Heartbeats that went unanswered, leading to connection close",
    registry=realtime_registry,
)

dispatch_latency_seconds = Histogram(
    "aifinops_realtime_dispatch_latency_seconds",
    "Time from event publish to being queued for a connection",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=realtime_registry,
)


def render_realtime_metrics() -> bytes:
    """Prometheus text-exposition-format bytes for just the real-time
    metrics — appended to the existing hand-written `/metrics` payload."""
    return generate_latest(realtime_registry)
