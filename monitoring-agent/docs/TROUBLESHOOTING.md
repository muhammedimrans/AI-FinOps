# Troubleshooting

## Startup

**`AgentAuthenticationError: No organization API key configured`**
No usable API key was found. Set one of: `organization.api_key` in
`config.yaml`, the `COSTORAH_AGENT_ORGANIZATION__API_KEY` environment
variable, or run `costorah-agent config set-key costorah_live_...` first.
See `CONFIGURATION.md`.

**`pydantic_core.ValidationError` on startup**
`config.yaml` failed schema validation — the error message names the exact
field and constraint that failed (e.g. `server.endpoint must start with
http:// or https://`). This is deliberate fail-fast behavior, not a bug.

**Collector doesn't appear in `/health`'s `collectors` list**
Either it isn't listed under `providers:` in `config.yaml`, or it's listed
but not `true`, or the provider name isn't in
`config.IMPLEMENTED_PROVIDERS` yet (grok/cohere/bedrock/mistral as of
EP-17 — enabling these is a recognized, silent no-op; see
`ARCHITECTURE.md`'s `CollectorRegistry.build_enabled` explanation).

## Collectors reporting unhealthy

**OpenAI: `"OPENAI_API_KEY not configured"`**
Set the `OPENAI_API_KEY` environment variable. It must be an **Admin**
key — a regular project key returns 401/403 against the org usage
endpoint (OpenAI's own restriction, not this agent's).

**Anthropic: `"ANTHROPIC_ADMIN_KEY not configured"`**
Set `ANTHROPIC_ADMIN_KEY` — distinct from a regular `ANTHROPIC_API_KEY`.
Usage reporting is admin-only on Anthropic's side.

**Anthropic collector silently returns no events even when configured**
By design: on any HTTP or JSON error from Anthropic's usage report API,
the collector logs a warning and returns `[]` rather than raising — this
mirrors the backend's own EP-08 Anthropic adapter, which treats usage
reporting as an optional capability. Check `/health` for the collector's
`detail` field, and agent logs for `anthropic_usage_fetch_failed`, to see
the underlying error.

**Google / Azure OpenAI always report `healthy: false`**
Expected — these are honest stubs in EP-17, not broken integrations. Real
usage data requires infrastructure this agent doesn't set up (GCP Billing
Export to BigQuery for Google; an Azure AD app registration + Cost
Management API access for Azure). The `detail` field explains this
explicitly. This is tracked as real follow-up work, not silently ignored.

**Ollama reports unreachable**
The collector does a real `GET {base_url}/api/tags` (default
`http://localhost:11434`) — confirm Ollama is actually running and
reachable from wherever the agent runs (a container needs
`base_url` pointed at the host, e.g. `http://host.docker.internal:11434`
on Docker Desktop, or the Ollama container's service name in Compose/K8s).
Note Ollama has no usage/cost API regardless — this collector never emits
usage events, only a connectivity signal.

## Delivery / queue

**`/health` shows `status: "degraded"` with `queue_size > 0`**
The agent has queued events it has never successfully delivered. Check:
COSTORAH `server.endpoint` reachability, TLS (`server.verify_tls`), and
whether the API key is valid (check agent logs for
`usage_event_delivery_failed` with `outcome: auth_failed`).

**Events stuck retrying indefinitely**
By design if the backend is genuinely down or the key is invalid —
`retry.max_attempts: null` (the default) means retry forever, which is
what "never lose telemetry" requires. Check `offline_store_size` in
`/health` and `costorah_agent_retries_total` in `/metrics` to confirm
events are queued, not lost. Once the underlying issue is fixed, the next
`Sender.run_once()` pass (every `min(interval_seconds, 5s)`) drains them
automatically — no manual replay needed.

**A specific event never delivers and doesn't show up in the retry store either**
It was likely dropped as `VALIDATION_FAILED` (HTTP 400/404/422 from the
ingestion API) — check logs for `usage_event_dropped_invalid`. This is
intentional: a malformed payload can never succeed no matter how many
times it's retried, so it's logged loudly and discarded rather than
retried forever. If you see this unexpectedly, it usually indicates a
collector bug producing an invalid `NormalizedUsageEvent` — file it as
such, referencing the logged `detail`.

## Logging

**Sensitive value showed up in a log line anyway**
Please report this — `logging_setup.redact_sensitive_fields` is meant to
catch known-sensitive key names (api_key, password, secret, token,
prompt, completion, etc., case-insensitive) and any embedded
`costorah_live_...` substring in *any* field, as a last line of defense.
If something slipped through, it's either a new sensitive field name the
redaction pattern list doesn't cover yet, or a bug.

## Known limitations (by design, not bugs)

- **No config hot-reload.** Changing `config.yaml` requires a restart.
- **No auto-updater.** Explicitly out of scope for EP-17 — the plugin
  architecture and `costorah-agent version` exist as the integration point
  for a future updater, not a shipped one.
- **`KeyStore` is not an OS-native secret store.** It's Fernet encryption
  with owner-only file permissions — real protection over plaintext, but
  not equivalent to Windows DPAPI / macOS Keychain / Linux Secret Service.
  Prefer the `COSTORAH_AGENT_ORGANIZATION__API_KEY` environment variable
  from your own secret manager in production.
- **`start --detach` is POSIX-only** and is a basic background mode for
  manual/dev use, not a production daemon — use systemd/Docker/Kubernetes
  for production (see `DEPLOYMENT.md`).
- **Provider credentials aren't in the `config.yaml` schema yet** — read
  from environment variables per-collector (see `CONFIGURATION.md`). A
  future phase may fold these into a `providers.<name>.*` config section.

## Getting more detail

Set `logging.level: DEBUG` in `config.yaml` (or
`COSTORAH_AGENT_LOGGING__LEVEL=DEBUG`) for verbose structured JSON logs to
stdout (and to `logging.file` if configured, rotated per
`max_bytes`/`backup_count`).
