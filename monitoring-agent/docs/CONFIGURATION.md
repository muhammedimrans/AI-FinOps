# Configuration Guide

## Precedence

**Environment variables > `config.yaml` > built-in defaults.**

Environment variables are prefixed `COSTORAH_AGENT_` and use `__` (double
underscore) as the nesting separator, e.g. `COSTORAH_AGENT_SERVER__ENDPOINT`
maps to `server.endpoint`. Values are coerced: `"true"`/`"false"` (any case)
become booleans, integer- and float-looking strings are parsed as such,
everything else stays a string.

Load a config file and print the effective (merged) configuration:

```bash
costorah-agent config show --config /etc/costorah-agent/config.yaml
```

The API key is always masked in `config show` output.

## `config.yaml` reference

See `config.example.yaml` at the repo root for a complete, valid file. Every
key below is optional — omitted keys use the default shown.

```yaml
server:
  endpoint: https://api.costorah.com   # must start with http:// or https://
  timeout_seconds: 10                  # per-request HTTP timeout
  verify_tls: true                     # disable ONLY for local dev against a self-signed backend

organization:
  api_key: ""                          # costorah_live_... — prefer the env var below in production

collection:
  interval_seconds: 5                  # how often each collector is polled
  batch_size: 50                       # max events per delivery batch

providers:
  openai: true
  anthropic: true
  google: true
  azure: true
  grok: false        # recognized, not yet implemented — enabling is a no-op
  openrouter: true
  ollama: false
  cohere: false       # recognized, not yet implemented — enabling is a no-op
  bedrock: false       # recognized, not yet implemented — enabling is a no-op
  mistral: false       # recognized, not yet implemented — enabling is a no-op

retry:
  backoff_seconds: [1, 2, 4, 8, 16, 30, 60]   # holds at the last value once exhausted
  max_attempts: null                          # null = retry forever (recommended: never lose telemetry)

queue:
  max_memory_events: 10000            # in-memory queue capacity before overflowing to disk
  sqlite_path: costorah-agent-queue.db  # durable offline retry store

logging:
  level: INFO                         # DEBUG | INFO | WARNING | ERROR | CRITICAL
  file: null                          # e.g. /var/log/costorah-agent/agent.log — omit for stdout only
  max_bytes: 10485760                 # 10MB, rotating file handler
  backup_count: 5

http_server:
  enabled: true
  host: 127.0.0.1                     # keep loopback-only unless you have a specific reason not to
  port: 9091
```

### Field validation

Invalid values fail fast at startup with a clear `pydantic` error, not a
silent fallback:

- `server.endpoint` must start with `http://` or `https://`.
- `organization.api_key`, if set, must start with `costorah_live_`.
- `providers` keys must be one of the ten catalog names above — a typo'd
  provider name is a startup error, not a silently-ignored no-op (that
  no-op behavior is reserved for *known, unimplemented* provider names).
- `retry.backoff_seconds` must be non-empty and every value positive.
- `logging.level` must be a standard Python logging level name.

## Supplying provider credentials

Per-provider credentials are **not** part of the top-level `config.yaml`
schema in EP-17 — they're read directly from environment variables by each
collector (see `ARCHITECTURE.md`'s collector table and each collector's own
module docstring for the exact variable name and required key type):

| Provider | Environment variable | Notes |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | Must be an **Admin** key — regular project keys can't read org-wide usage. |
| Anthropic | `ANTHROPIC_ADMIN_KEY` | Distinct from a regular API key; usage reporting is admin-only. |
| OpenRouter | `OPENROUTER_API_KEY` | Standard OpenRouter key. |
| Ollama | *(none — `base_url` only, default `http://localhost:11434`)* | No usage API exists; this is a connectivity check only. |
| Google, Azure | *(not applicable yet)* | Honest stubs — see `ARCHITECTURE.md`. |

This is a deliberate scope boundary for this phase, not an oversight — see
`docs/TROUBLESHOOTING.md` for the reasoning and the planned follow-up
(bringing these into the `providers.<name>.*` config schema once the
underlying collectors support it, e.g. once the Google/Azure integrations
move past the stub tier).

## Supplying the COSTORAH organization API key

Three ways, in order of recommendation:

1. **Environment variable (recommended for production):**
   ```bash
   export COSTORAH_AGENT_ORGANIZATION__API_KEY=costorah_live_xxxxxxxxxxxx
   ```
2. **Encrypted key store:**
   ```bash
   costorah-agent config set-key costorah_live_xxxxxxxxxxxx
   ```
   Encrypts the key with Fernet and writes `keystore.key` / `keystore.enc`
   (owner-only permissions on POSIX) to the current directory. See
   `docs/DEVELOPER_GUIDE.md` for the scope limitations of this approach
   versus an OS-native secret store.
3. **Plaintext in `config.yaml`** (`organization.api_key`) — simplest for
   local development, not recommended for production since anyone who can
   read the file gets the key.

## Reloading configuration

There is no hot-reload in EP-17 — changing `config.yaml` requires
restarting the agent process (`costorah-agent stop` then `start`, or let
your supervisor restart it). This is a known limitation, not an oversight;
see `docs/TROUBLESHOOTING.md`.
