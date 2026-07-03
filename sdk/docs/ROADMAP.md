# COSTORAH SDK Roadmap

EP-18 ("Build the official COSTORAH SDK ecosystem") is being delivered in
four phases, per the ticket's own recommendation, to keep each deliverable
focused, testable, and independently reviewable.

## EP-18.1 — SDK Core ✅ Shipped

- Python (`pip install costorah`) and JavaScript/TypeScript
  (`npm install @costorah/sdk`) packages.
- Configuration, EP-15 Bearer authentication, HTTP client with bounded
  exponential-backoff retry.
- Manual `track()` with client-side validation.
- SDK-specific exceptions (`AuthenticationError`, `ValidationError`,
  `RateLimitError`, `ServerError`, `NetworkError`).
- Redacted structured logging (never logs API keys, prompts, or
  responses).
- Thread safety (Python) / async-concurrency safety (JavaScript).
- Unit, integration, and performance test suites for both languages.
- PyPI/npm packaging metadata (build verified locally; publish itself is
  a release-time action, not part of this phase).

## EP-18.2 — Automatic Instrumentation ✅ Shipped

- `BaseInstrumentor` plugin architecture (Python `costorah.instrumentation`,
  JS `@costorah/sdk`'s `src/instrumentation`) — `instrument()`,
  `uninstrument()`, `isInstrumented()`, `extractUsage()`, `normalize()`.
- All 10 required providers: OpenAI, Azure OpenAI, OpenRouter, Ollama,
  Grok, Anthropic, Mistral, Amazon Bedrock, Google Gemini, Cohere.
- Safe, restorable monkey patching of official SDK methods only; sync and
  async; streaming (telemetry sent only after the stream completes).
- Automatic cost calculation via a shared per-token pricing table when a
  provider response doesn't include cost; unknown models report cost `0`,
  never a guess.
- Privacy-preserving by construction: only usage metadata is ever read
  from a response, never prompt/completion content.
- See `sdk/docs/AUTOMATIC_INSTRUMENTATION.md` for the full guide.

## EP-18.3 — Enterprise Reliability Layer ✅ Shipped

- Full pipeline: Memory Queue → Background Worker → Persistent Queue →
  Compression → Retry Engine → Circuit Breaker → Connection Pool → Usage
  API. `track()` validates synchronously and enqueues — verified <1ms —
  never making a blocking network call.
- Configurable overflow policy (`drop_newest`/`drop_oldest`/`block`),
  gzip compression above a size threshold, the ticket's exact
  exponential-backoff schedule (never-retry on 4xx), and a genuinely new
  Closed/Open/Half-Open circuit breaker (EP-17's Monitoring Agent had no
  circuit-breaker concept to reuse).
- Crash-durable persistent queue: SQLite (Python, reusing EP-17's
  offline-store shape) / a zero-dependency newline-delimited-JSON append
  log (JavaScript, since adding LevelDB would break the SDK's
  zero-runtime-dependency guarantee).
- `client.flush()`/`shutdown()`/`health()`/`queue_stats()` (Python) and
  their JS equivalents for callers that need delivery confirmation.
- At-least-once delivery guarantee, explicitly documented (never
  exactly-once — relies on EP-16's existing `request_id` idempotency).
- See `sdk/docs/RELIABILITY.md` for the full guide, including the
  explicit, honest scope note on "batch upload" (EP-16 has no
  multi-event ingestion endpoint, so batching here means concurrent
  pipelined delivery of individual events, not fewer HTTP requests than
  events).

## EP-18.4 — Ecosystem, CLI, FastAPI/Express, Publishing ✅ Shipped

- Python FastAPI middleware (`costorah.integrations.fastapi.
  CostorahMiddleware`) and JS Express middleware
  (`@costorah/sdk/express`'s `costorahMiddleware()`), both built on a
  new ambient request-context primitive (`costorah.context` /
  `context.ts`) that every later framework integration reuses.
- `costorah` CLI (`init`/`doctor`/`health`/`version`/`config`).
- CI/CD (GitHub Actions, both SDKs) and a tag-gated publish workflow;
  LICENSE/CHANGELOG/RELEASE.md ahead of the v1.0.0 public release.
- `SECURITY.md`, `PERFORMANCE.md`, `FRAMEWORK_INTEGRATIONS.md`,
  `CLI.md`; one runnable example app per language.
- See the EP-18.4 final report for the explicit list of what was
  scoped out (most framework integrations beyond FastAPI/Express, the
  AI-framework auto-capture integrations, the interactive config
  wizard, the full example-app matrix) — most of the Python portion of
  that list was then picked up by EP-18.5.

## EP-18.5 — Python Framework Integrations ✅ Shipped

- Flask (`costorah.integrations.flask.CostorahExtension` — direct init
  and application-factory pattern, blueprint- and multi-app-safe),
  Django (`costorah.integrations.django.CostorahMiddleware` — dual
  sync/async, settings-based config, a `manage.py costorah_doctor`
  management command), Starlette standalone (a deliberate re-export of
  the FastAPI middleware — no duplicate implementation), Celery
  (`costorah.integrations.celery.CostorahCelery` — signal-based ambient
  context around task execution), and generic ASGI/WSGI middleware
  (framework-agnostic, what `CostorahExtension` wraps internally).
- `costorah doctor` gained a Framework version compatibility check
  (advisory, never flips the exit code) for all five Python
  integrations.
- `sdk/docs/FLASK.md`, `DJANGO.md`, `CELERY.md`, `ASGI_WSGI.md`; example
  apps for Flask, Django, Celery.
- JavaScript framework integrations (NestJS, Next.js, Cloudflare
  Workers, Vercel, AWS Lambda, Bun, Deno) and the AI-framework
  auto-capture integrations (LangChain, LlamaIndex, CrewAI, AutoGen,
  Semantic Kernel, Haystack, MCP) were explicitly out of scope for this
  Python-only EP — see the EP-18.5 final report.

## Explicitly out of scope for the whole EP-18 initiative

Per the ticket: billing, AI recommendations, a live dashboard, WebSockets,
changes to the Monitoring Agent (EP-17), and backend changes beyond what's
strictly required to support the SDKs (none were required — EP-18.1 reuses
EP-15/EP-16 as-is).

## Future languages (interfaces designed for, not yet implemented)

Go, Java, C#, Rust. `sdk/shared/API_CONTRACT.md` is written so any of
these can be implemented from that document alone, matching the same
configuration keys, error taxonomy, and retry semantics as Python and
JavaScript — this is the point of writing it down as a language-agnostic
contract now, rather than after a second language SDK.
