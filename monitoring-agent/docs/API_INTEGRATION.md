# API Integration Guide

How the agent talks to COSTORAH, and how the agent's own local API works.

## Outbound: Usage Ingestion (EP-16)

**Endpoint:** `POST {server.endpoint}/v1/ingest/usage`
**Auth:** `Authorization: Bearer costorah_live_...` (Organization API Key, EP-15)

The agent sends exactly the payload `NormalizedUsageEvent.to_ingestion_payload()`
produces (`costorah_agent/collectors/models.py`), which matches EP-16's
`IngestUsageRequest` schema field-for-field:

```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "request_id": "agent_3f9a2b1c...",
  "input_tokens": 100,
  "output_tokens": 50,
  "total_tokens": 150,
  "cost": 0.0021,
  "currency": "USD",
  "status": "success",
  "timestamp": "2026-07-02T12:00:00+00:00",
  "metadata": {}
}
```

Optional fields (`cached_tokens`, `latency_ms`, `region`, `project_id`) are
omitted entirely when `None` rather than sent as JSON `null`.

### Response handling (`transport/http_client.py`)

| HTTP status | Outcome | Agent behavior |
|---|---|---|
| 200, `duplicate: false` | `SUCCESS` | Remove from retry store; count as sent |
| 200, `duplicate: true` | `DUPLICATE` | Remove from retry store; count as duplicate (not an error — EP-16's own dedup working as intended) |
| 401, 403 | `AUTH_FAILED` | Retry with backoff; logged at `error` level every attempt (likely a config problem) |
| 400, 404, 422 | `VALIDATION_FAILED` | Drop permanently, logged at `error` level (retrying a malformed payload can never succeed) |
| 5xx, timeout, connection error | `RETRYABLE_ERROR` | Retry with backoff; logged at `warning` level |

### Idempotency

Every event carries a stable `request_id` (`deterministic_request_id()`,
`collectors/_util.py` — SHA-256 over the fields that uniquely identify the
underlying usage record, e.g. bucket start/end time + model). Re-polling an
overlapping time window naturally produces the *same* `request_id` for the
same underlying usage, which EP-16's `(organization_id, request_id)` unique
constraint then dedupes server-side. The agent never needs its own
separate dedup logic — it relies on this contract.

## Inbound: the agent's own local HTTP API

Bound to `127.0.0.1:9091` by default (`http_server.host`/`port` in
`config.yaml`) — not exposed off-host unless explicitly reconfigured.

### `GET /health`

```json
{
  "status": "healthy",
  "queue_size": 0,
  "offline_store_size": 0,
  "last_upload": "2026-07-02T12:00:03.412Z",
  "version": "0.1.0",
  "started_at": "2026-07-02T11:55:00.000Z",
  "collectors": [
    {
      "name": "openai",
      "enabled": true,
      "healthy": true,
      "detail": "ok",
      "last_collected_at": "2026-07-02T12:00:00.000Z",
      "events_collected_total": 42
    }
  ]
}
```

`status` is `"degraded"` when either: the in-memory queue has items but the
agent has never successfully uploaded anything, or any enabled collector
reports `healthy: false`. Otherwise `"healthy"`.

`costorah-agent health` (CLI) hits this endpoint and exits non-zero when
`status != "healthy"` — suitable for a container `HEALTHCHECK` or a
deploy-gate script.

### `GET /metrics`

Prometheus text exposition format (`server/metrics.py`):

```
# HELP costorah_agent_queue_size Events currently in the in-memory queue
# TYPE costorah_agent_queue_size gauge
costorah_agent_queue_size 0
# HELP costorah_agent_events_sent_total Usage events successfully ingested
# TYPE costorah_agent_events_sent_total counter
costorah_agent_events_sent_total 142
...
costorah_agent_events_by_provider_total{provider="openai"} 89
costorah_agent_events_by_provider_total{provider="openrouter"} 53
...
costorah_agent_info{version="0.1.0"} 1
```

Full metric list: `costorah_agent_queue_size`,
`costorah_agent_offline_store_size`, `costorah_agent_events_sent_total`,
`costorah_agent_events_duplicate_total`, `costorah_agent_events_failed_total`,
`costorah_agent_retries_total`, `costorah_agent_uploads_total`,
`costorah_agent_last_latency_ms`, `costorah_agent_avg_latency_ms`,
`costorah_agent_events_by_provider_total{provider="..."}`,
`costorah_agent_info{version="..."}`.

## Dashboard integration

No frontend changes ship with EP-17, and none are needed: the agent
delivers into the same `POST /v1/ingest/usage` endpoint EP-16 built, which
already writes into the tables the existing dashboard APIs read from.
Once the agent is running with a valid API key and at least one collector
producing real events, dashboard data reflects it automatically.
