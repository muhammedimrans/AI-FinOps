"""
Prometheus text-format renderer for the agent's own metrics.

Pure function, no I/O, independently testable against a metrics snapshot —
kept separate from the aiohttp route handler in app.py on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass

from costorah_agent.transport.sender import SenderMetrics


@dataclass(slots=True)
class MetricsSnapshot:
    queue_size: int
    store_size: int
    sender: SenderMetrics
    version: str


def render_prometheus(snapshot: MetricsSnapshot) -> str:
    lines: list[str] = []

    def counter(name: str, help_text: str, value: float) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {value}")

    def gauge(name: str, help_text: str, value: float) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value}")

    gauge(
        "costorah_agent_queue_size",
        "Events currently in the in-memory queue",
        snapshot.queue_size,
    )
    gauge(
        "costorah_agent_offline_store_size",
        "Events currently persisted in the durable SQLite retry store",
        snapshot.store_size,
    )
    counter(
        "costorah_agent_events_sent_total",
        "Usage events successfully ingested",
        snapshot.sender.events_sent_total,
    )
    counter(
        "costorah_agent_events_duplicate_total",
        "Usage events resolved as duplicates by the ingestion API",
        snapshot.sender.events_duplicate_total,
    )
    counter(
        "costorah_agent_events_failed_total",
        "Usage events permanently dropped after a non-retryable error",
        snapshot.sender.events_failed_total,
    )
    counter(
        "costorah_agent_retries_total",
        "Delivery attempts that resulted in a retry",
        snapshot.sender.retries_total,
    )
    counter(
        "costorah_agent_uploads_total",
        "Total HTTP delivery attempts (success or failure)",
        snapshot.sender.uploads_total,
    )
    gauge(
        "costorah_agent_last_latency_ms",
        "Latency of the most recent delivery attempt",
        snapshot.sender.last_latency_ms,
    )
    gauge(
        "costorah_agent_avg_latency_ms",
        "Average latency across all delivery attempts",
        snapshot.sender.avg_latency_ms,
    )

    lines.append("# HELP costorah_agent_events_by_provider_total Usage events sent, by provider")
    lines.append("# TYPE costorah_agent_events_by_provider_total counter")
    for provider, count in sorted(snapshot.sender.events_by_provider.items()):
        lines.append(f'costorah_agent_events_by_provider_total{{provider="{provider}"}} {count}')

    lines.append("# HELP costorah_agent_info Agent build information")
    lines.append("# TYPE costorah_agent_info gauge")
    lines.append(f'costorah_agent_info{{version="{snapshot.version}"}} 1')

    return "\n".join(lines) + "\n"
