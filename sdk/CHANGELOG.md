# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Both the Python (`costorah` on PyPI) and JavaScript (`@costorah/sdk` on
npm) packages are versioned together under [Semantic Versioning](https://semver.org/)
— see `RELEASE.md` for the version-compatibility matrix and deprecation
policy.

## [1.0.0] — EP-18.4

First public release. Ships all four EP-18 phases together:

### Added

- **SDK Core (EP-18.1)**: `Costorah` client, manual `track()`, EP-15
  Bearer authentication, configuration, SDK-specific exceptions,
  redacted structured logging.
- **Automatic Instrumentation (EP-18.2)**: `BaseInstrumentor` plugin
  architecture; instrumentors for OpenAI, Azure OpenAI, OpenRouter,
  Ollama, Grok, Anthropic, Mistral, Amazon Bedrock, Google Gemini, and
  Cohere. Safe, restorable monkey-patching; sync and async; streaming;
  automatic cost calculation; privacy-preserving by construction (only
  usage metadata is ever read).
- **Enterprise Reliability Layer (EP-18.3)**: Memory Queue → Background
  Worker → Persistent Queue → Compression → Retry Engine → Circuit
  Breaker → Connection Pool pipeline. `track()` now enqueues and returns
  in <1ms instead of blocking on network. `client.flush()`/`shutdown()`/
  `health()`/`queue_stats()` added.
- **Ecosystem & Public Release (EP-18.4)**:
  - `costorah.integrations.fastapi.CostorahMiddleware` (Python) and
    `costorahMiddleware()` from `@costorah/sdk/express` (JavaScript) —
    auto-initialization and per-request context capture.
  - `costorah` CLI (`init`, `doctor`, `health`, `version`, `config`).
  - `costorah.context`/JS `context.ts` — ambient request context
    (contextvars / AsyncLocalStorage) shared by every framework
    integration.
  - CI/CD: GitHub Actions for lint/typecheck/test/build (both SDKs,
    matrixed across supported Python/Node versions) and a separate
    tag-gated publish workflow.
  - `sdk/docs/RELEASE.md`, this changelog, and `LICENSE` files in both
    package directories.

### Changed

- `TrackResult` (Python) / `TrackResult` (JavaScript): `usage_id`/
  `processed_at`/`duplicate` are no longer populated synchronously by
  `track()` — see EP-18.3's note in `sdk/docs/RELIABILITY.md`. This is
  the one user-visible breaking-ish change from the pre-1.0 development
  snapshots; there was no prior public release to migrate from.

### Known limitations

See `sdk/docs/ROADMAP.md` and the EP-18.4 final report for what's
explicitly deferred: most framework integrations beyond FastAPI/Express
(Flask, Django, Celery, LangChain, NestJS, Next.js, etc.), the
interactive configuration wizard, and the full example-app matrix.
