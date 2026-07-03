"""Real Prometheus instrumentation for the alert engine — EP-19.3.

Same pattern as `app.realtime.metrics` (EP-19.1): its own
`CollectorRegistry`, appended to `GET /metrics` alongside the realtime
payload — not merged into either the hand-written static block or the
realtime registry.
"""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

alerts_registry = CollectorRegistry()

alerts_created_total = Counter(
    "aifinops_alerts_created_total",
    "Alerts created (new dedup group opened)",
    ["alert_type", "severity"],
    registry=alerts_registry,
)

alerts_delivered_total = Counter(
    "aifinops_alerts_delivered_total",
    "Alerts published to the real-time event bus for live delivery",
    ["alert_type"],
    registry=alerts_registry,
)

alerts_acknowledged_total = Counter(
    "aifinops_alerts_acknowledged_total",
    "Alerts acknowledged by a user",
    ["alert_type"],
    registry=alerts_registry,
)

alerts_suppressed_total = Counter(
    "aifinops_alerts_suppressed_total",
    "Alert firings skipped due to an active suppression",
    ["alert_type"],
    registry=alerts_registry,
)

alerts_deduplicated_total = Counter(
    "aifinops_alerts_deduplicated_total",
    "Occurrences folded into an existing open alert instead of creating a new one",
    ["alert_type"],
    registry=alerts_registry,
)

notification_latency_seconds = Histogram(
    "aifinops_alerts_notification_latency_seconds",
    "Time to publish a fired alert to the event bus",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=alerts_registry,
)

rule_evaluation_latency_seconds = Histogram(
    "aifinops_alerts_rule_evaluation_latency_seconds",
    "Time to evaluate an organization's rules for one alert type",
    buckets=(0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
    registry=alerts_registry,
)


def render_alerts_metrics() -> bytes:
    return generate_latest(alerts_registry)
