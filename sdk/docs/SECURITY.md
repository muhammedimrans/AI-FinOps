# Security Review (EP-18.4)

## What's never persisted or logged

Verified by direct code review plus dedicated tests (both SDKs' privacy
tests in `sdk/*/tests/instrumentation/*.test.*` assert captured payloads
never contain literal prompt/completion text used in each test):

- **API keys / secrets**: both SDKs' logging modules (`costorah/_logging.py`,
  `src/logging.ts`) redact key-like fields before any log line is
  emitted, even at debug level. The CLI's `config`/`doctor` output masks
  the API key (`costorah_live_ab...wxyz`), never printing it in full.
- **Prompt text / completion text / images / files / audio / embeddings**:
  every `extractUsage()`/`extract_usage()` implementation across all 10
  provider instrumentors reads only a response's usage/token-count
  fields — never its content fields. This is structural (the extraction
  functions have no code path that touches message/choice content), not
  a filter applied after the fact.
- **Request bodies in framework integrations**: `CostorahMiddleware`
  (Python) and `costorahMiddleware()` (JS) capture only request ID,
  path, method, and an optional `organizationId` — never headers,
  query params, or the request body.

## Ambient request context (EP-18.4-specific)

The new `costorah.context`/`context.ts` modules attach ambient metadata
(`request_context`/`requestContext`) to usage events during a request.
This is opt-in (only populated when a framework integration is in use)
and only ever contains what the integration explicitly sets — request
ID, path, HTTP method, organization ID. It cannot capture arbitrary
request data (headers, body, query string) because nothing in the
middleware reads those into the context in the first place.

## Dependency audit

**Python** (`sdk/python/pyproject.toml`): one runtime dependency,
`httpx>=0.25` — a widely-used, actively maintained HTTP client with no
known critical advisories as of this review. Dev-only dependencies
(pytest, ruff, mypy, provider SDKs, fastapi) never ship in the published
package.

**JavaScript** (`sdk/javascript/package.json`): **zero runtime
dependencies** (verified — no `dependencies` key in `package.json`;
Node's built-in `fetch`, `zlib`, `fs/promises`, and `async_hooks` cover
everything the reliability layer and framework integrations need). This
was a deliberate design constraint through EP-18.3/EP-18.4 specifically
to keep the security/supply-chain surface minimal — see
`RELIABILITY.md`'s note on why the persistent queue doesn't use LevelDB.

Dev dependencies carry a small number of transitive advisories (`npm
audit`: vite/esbuild, pulled in by `vitest`) — these affect only the
local dev server used while running tests, are not reachable in CI (no
dev server is started), and do not ship in the published package (only
`dist/` is published, per `package.json`'s `files` field). Bumping
`vitest` to clear them is a breaking major-version change deferred to a
future release rather than rushed into this one.

## Supply chain

- **Publishing**: PyPI via Trusted Publishing (OIDC, no long-lived token
  in the repo); npm via a repository secret (`NPM_TOKEN`) scoped to
  publish access only. See `RELEASE.md`.
- **CI**: every push/PR runs lint + type check + tests + build for both
  SDKs (`.github/workflows/ci.yml`) before anything can be tagged for
  release; the publish workflow re-runs the same verification
  independently before publishing (never trusts a stale CI run).

## License compliance

MIT (matches the repository root `LICENSE`, copied into both
`sdk/python/LICENSE` and `sdk/javascript/LICENSE` for inclusion in the
published packages). `httpx` is BSD-3-Clause; every JS dev dependency's
license was not individually re-audited in this pass (none ship in the
published `@costorah/sdk` package, so they don't affect its license
terms).

## What this review did not (and could not) cover

- **Runtime penetration testing** of the live COSTORAH backend (EP-16)
  — out of scope for an SDK-side Engineering Package.
- **Continuous dependency scanning**: an automated tool (Dependabot,
  Snyk, etc.) wired into CI is not set up as part of this pass; the
  audit above is a one-time manual check, not continuous monitoring.
