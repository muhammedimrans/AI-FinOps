# COSTORAH SDK Wire Contract

This is the language-agnostic contract every COSTORAH SDK (Python,
JavaScript today; Go/Java/C#/Rust in the future) implements against. A new
language SDK should be able to be written from this document alone,
without reading another SDK's source.

## Authentication (reuses EP-15 — do not modify)

Every request carries:

```
Authorization: Bearer costorah_live_xxxxxxxxxxxxxxxxxxxx
```

The key is validated by `POST /v1/ingest/usage`'s existing EP-15
middleware (`RequireApiKeyPermission(Permission.USAGE_WRITE)`). SDKs do
not implement their own auth logic beyond attaching this header — there is
no separate SDK-side auth handshake, token exchange, or session.

**Never log, print, or include the API key in an error message body.**
Every SDK's logger must redact it (see `LOGGING.md`).

## Ingestion endpoint (reuses EP-16 — do not modify)

```
POST {endpoint}/v1/ingest/usage
Content-Type: application/json
Authorization: Bearer {api_key}
```

Default `endpoint`: `https://api.costorah.com`.

### Request body

One event per request in EP-18.1 (SDK Core). EP-18.3 (batching, not yet
implemented) will send multiple events as multiple sequential requests
from a single flush — the ingestion API itself is single-event; there is
no server-side batch endpoint to build for.

```json
{
  "provider": "openai",
  "model": "gpt-4.1",
  "request_id": "sdk_py_3f9a2b1c...",
  "input_tokens": 500,
  "output_tokens": 220,
  "total_tokens": 720,
  "cost": 0.041,
  "currency": "USD",
  "latency_ms": 621,
  "status": "success",
  "timestamp": "2026-07-02T18:15:22+00:00",
  "metadata": {}
}
```

Field semantics exactly match `backend/app/schemas/usage_ingestion.py`'s
`IngestUsageRequest` (EP-16) — an SDK must not invent additional required
fields or rename any of these:

| Field | Type | Required | Notes |
|---|---|---|---|
| `provider` | string | yes | Must be one of the EP-16 provider catalog (see below) |
| `model` | string | yes | Non-blank |
| `project_id` | UUID string | no | Omit if unknown — never send an empty string |
| `request_id` | string | yes | SDK-generated if the caller doesn't supply one — see Idempotency below |
| `input_tokens` | integer ≥ 0 | no (default 0) | |
| `output_tokens` | integer ≥ 0 | no (default 0) | |
| `cached_tokens` | integer ≥ 0 | no | Must not exceed `input_tokens` |
| `total_tokens` | integer ≥ 0 | no | If sent, must equal `input_tokens + output_tokens` — SDKs should omit this and let the server derive it rather than risk a mismatch, unless the caller explicitly overrides it |
| `cost` | number ≥ 0 | yes | Decimal-precision on the wire; SDKs may accept a float/number client-side |
| `currency` | string | no (default `"USD"`) | 3–8 alphabetic characters |
| `latency_ms` | integer ≥ 0 | no | |
| `status` | `"success" \| "error" \| "timeout" \| "cancelled"` | no (default `"success"`) | |
| `region` | string | no | |
| `timestamp` | ISO-8601 string | no | Server defaults to "now" if omitted; must not be more than 300s in the future |
| `metadata` | object | no (default `{}`) | Must serialize to ≤ 16KB JSON |

### Provider catalog

SDKs must accept exactly these provider slugs (from
`backend/app/models/provider_connection.py::ProviderType` — the same
catalog EP-17's Monitoring Agent uses):

```
openai, anthropic, grok, google, azure_openai, openrouter, ollama, cohere, bedrock, mistral
```

An SDK's `track()` must reject (client-side, before making an HTTP call)
any provider string outside this set with a `ValidationError`, saving a
round trip for an error the SDK can already detect.

### Idempotency (`request_id`)

Reusing the same `request_id` for the same organization is not an error —
the original record is returned with `duplicate: true` and HTTP 200
(Stripe's `Idempotency-Key` convention). SDKs should generate a stable,
deterministic `request_id` when the caller doesn't supply one (e.g. a hash
of provider + model + timestamp + a random nonce, or — for automatic
instrumentation in EP-18.2 — a hash derived from the underlying provider
response's own request ID when the provider exposes one), so accidental
double-sends (e.g. a retried HTTP call) are deduplicated server-side rather
than double-counted.

### Responses

**200 — success or resolved duplicate:**
```json
{
  "success": true,
  "usage_id": "5b1e2b2e-6b1a-4b8e-9b1a-5b1e2b2e6b1a",
  "request_id": "sdk_py_3f9a2b1c...",
  "processed_at": "2026-07-02T18:15:22Z",
  "duplicate": false
}
```

**Error status → SDK exception mapping** (every SDK must map identically):

| HTTP status | SDK exception | Retry? |
|---|---|---|
| 401 | `AuthenticationError` | No — client misconfiguration (bad/expired key) |
| 403 | `AuthenticationError` | No — organization suspended or key lacks `usage:write` |
| 400, 404, 422 | `ValidationError` | No — payload itself is invalid; retrying an unchanged payload can never succeed |
| 429 | `RateLimitError` | Yes, honoring `Retry-After` if present, else the configured backoff schedule |
| 5xx | `ServerError` | Yes, with exponential backoff |
| Network/timeout (no response) | `NetworkError` | Yes, with exponential backoff |

Backoff schedule (matches EP-17's `RetryPolicy` exactly, for consistency
across the whole COSTORAH ecosystem): `1, 2, 4, 8, 16, 30, 60` seconds,
holding at 60s once exhausted.

## Configuration keys (must exist, with these exact semantics, in every SDK)

| Key | Default | Meaning |
|---|---|---|
| `api_key` | — (required) | `costorah_live_...` |
| `endpoint` | `https://api.costorah.com` | Ingestion API base URL |
| `timeout` | 30s | Per-request HTTP timeout |
| `batch_size` | 25 | Events per batch flush (EP-18.3) |
| `flush_interval` | 5s | Max time before an incomplete batch is flushed anyway (EP-18.3) |
| `max_retries` | 3 | Bounded retry count for a single synchronous `track()` call in EP-18.1's core client. (EP-18.3's background queue retries indefinitely, matching the Monitoring Agent's "never lose telemetry" posture — that's a queue-drain concern, not a blocking-call concern.) |

## What's implemented in EP-18.1 vs later phases

- **EP-18.1 (this phase):** configuration, EP-15 auth, HTTP client with
  bounded exponential-backoff retry for transient failures, manual
  `track()`, error classes, redacted structured logging, packaging.
- **EP-18.2 (not yet built):** automatic provider-response detection and
  normalization (`track_openai()`, `track_anthropic()`, etc.) and
  auto-instrumentation wrappers.
- **EP-18.3 (not yet built):** background batching, an in-process queue,
  offline persistence, and indefinite retry — conceptually reusing EP-17's
  Memory Queue → Retry Queue → HTTP Sender design, adapted for an
  in-process SDK rather than a standalone agent process.
- **EP-18.4 (not yet built):** framework integrations, expanded docs,
  examples, SDK-specific CI/CD, and 1.0 release polish.
