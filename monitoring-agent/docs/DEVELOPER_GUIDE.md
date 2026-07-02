# Developer Guide

## Project layout

```
monitoring-agent/
├── costorah_agent/
│   ├── agent.py              # Agent — orchestrator (lifecycle, collection/delivery loops)
│   ├── cli.py                # click CLI: start/stop/status/config/version/health
│   ├── config.py             # AgentConfig (pydantic) — YAML + env var loading/validation
│   ├── logging_setup.py      # structlog config + mandatory secret redaction
│   ├── version.py            # single source of truth for __version__
│   ├── collectors/
│   │   ├── base.py           # BaseCollector ABC — the plugin interface
│   │   ├── registry.py       # CollectorRegistry — name -> BaseCollector subclass
│   │   ├── models.py         # NormalizedUsageEvent, CollectorHealth
│   │   ├── _util.py          # deterministic_request_id, env_or_config
│   │   ├── openai.py         # real collector
│   │   ├── openrouter.py     # real collector
│   │   ├── anthropic.py      # real collector, honest degradation on error
│   │   ├── google.py         # honest stub
│   │   ├── azure_openai.py   # honest stub
│   │   └── ollama.py         # real connectivity check, no usage API
│   ├── queue/
│   │   ├── memory_queue.py   # EventQueue — bounded in-memory, overflows to disk
│   │   ├── sqlite_store.py   # SQLiteEventStore — durable offline retry queue
│   │   └── retry.py          # RetryPolicy — exponential backoff schedule
│   ├── transport/
│   │   ├── http_client.py    # HttpClient — POST /v1/ingest/usage, Bearer auth
│   │   └── sender.py         # Sender — drains queue+store, applies retry policy
│   ├── security/
│   │   └── key_store.py      # KeyStore — Fernet-encrypted API key at rest
│   └── server/
│       ├── app.py            # aiohttp app: /health, /metrics
│       └── metrics.py        # Prometheus text-format renderer (pure function)
├── tests/
│   ├── unit/                 # no network I/O; MockTransport for HTTP-calling code
│   ├── integration/          # real Agent + queue + sender wired together, HTTP mocked
│   └── performance/          # 10,000-event queue depth, memory/CPU, retry timing
├── packaging/                # systemd, Windows, Docker, Kubernetes
├── docs/                     # this directory
├── config.example.yaml
└── pyproject.toml
```

## Setting up a dev environment

```bash
cd monitoring-agent
python3.12 -m venv .venv
source .venv/bin/activate       # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

## Running the test suite

```bash
pytest tests/unit tests/integration -q     # fast, ~2s
pytest tests/performance -q                # slower, disk-bound (~60s)
pytest -q                                  # everything
```

## Linting and type checking

```bash
ruff check costorah_agent tests
ruff format costorah_agent tests
mypy costorah_agent      # strict mode; tests/ is intentionally not mypy-strict
```

## Writing a new collector

1. Subclass `BaseCollector` in a new file under `costorah_agent/collectors/`.
2. Set `name` to the provider slug used in the EP-16 ingestion catalog.
3. Implement `collect()` (async, does the real I/O), `normalize()` (sync,
   pure — no I/O, so it's testable against a fixture dict with zero
   network calls), and `health()` (async, must never raise).
4. If your collector genuinely can't get real usage/cost data with the
   credentials you have, don't fabricate a number — follow the
   `google.py`/`azure_openai.py` honest-stub pattern: `collect()` returns
   `[]`, `normalize()` raises `NotImplementedError` with a clear message,
   `health()` reports `healthy=False` with that same message.
5. Register it in `collectors/registry.py`'s `register_builtin_collectors()`.
6. Add it to `config.py`'s `IMPLEMENTED_PROVIDERS` frozenset (the
   `_ALL_PROVIDERS` tuple already reserves the slug if it's one of the ten
   catalog providers; if it's a genuinely new provider not yet in COSTORAH's
   catalog, coordinate with the backend's provider catalog first — see
   EP-16).
7. Write `tests/unit/test_collectors.py` cases: at minimum, a
   `normalize()` test against a realistic fixture payload, and a
   `collect()`-without-credentials test. If the collector makes real HTTP
   calls, add success/error-path tests using `httpx.MockTransport` (the
   collector's constructor accepts an optional `transport=` kwarg for
   exactly this — see any of the four real-network collectors for the
   pattern).

No other file needs to change — this is the point of the plugin
architecture (see `ARCHITECTURE.md`).

## Adding a framework/SDK integration (LangChain, CrewAI, MCP servers, etc.)

Same process as above: these are just another `BaseCollector` subclass.
A framework callback hook would call `collect()`'s underlying logic (or
push directly into a queue the collector exposes) instead of polling a
REST API — the *interface* the rest of the agent depends on
(`collect`/`normalize`/`health`/`shutdown`) doesn't change. This is the
reason EP-17 chose a common collector interface from the start rather than
provider-specific ad-hoc code paths.

## Security posture for contributors

- Never log an API key, a user prompt, or a model response — even in a
  `log.debug()` call. `logging_setup.redact_sensitive_fields` is a
  last-line-of-defense, not a substitute for not passing secrets to a
  logger in the first place.
- If you add a new HTTP client, thread through `verify_tls` from config —
  don't hardcode certificate verification off, even for a "just this one
  provider" special case.
- `KeyStore` (`security/key_store.py`) is honestly documented as *not*
  equivalent to an OS-native secret store. Don't market it as one in new
  docs or error messages.

## Release process

1. Bump `costorah_agent/version.py`.
2. `ruff check`, `ruff format --check`, `mypy costorah_agent`, `pytest`.
3. Build: `python -m build --wheel` (this is exactly what
   `packaging/docker/Dockerfile`'s build stage does).
4. Tag and publish per your organization's normal release process — EP-17
   does not include a PyPI/registry publish step or an auto-updater (see
   `TROUBLESHOOTING.md` for why auto-update is architecture-only in this
   phase).
