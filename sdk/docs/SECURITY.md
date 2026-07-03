# Security Review (EP-18.4, EP-18.5, EP-18.6)

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
  (Python FastAPI/Starlette/Django, JS Express/NestJS),
  `CostorahExtension` (Flask), `CostorahASGIMiddleware`/
  `CostorahWSGIMiddleware`, `costorahNodeMiddleware`, `costorahLambda`,
  `costorahWorker`, `costorahHandler`/`costorahApiRoute` (Next.js) all
  capture only request ID, path/route, method, and an optional
  organization ID — never headers (beyond `X-Request-Id`), query params,
  cookies, or the request body.
- **Lambda event payloads (EP-18.6)**: `costorahLambda` reads only the
  fields needed to classify an event's shape and extract route/method
  (`httpMethod`/`path`/`rawPath`/`requestContext.http.method`) — it
  never reads or logs the request body, and for non-HTTP events
  (EventBridge/SQS/SNS) captures nothing beyond `context.awsRequestId`
  as the ambient request ID, never the event's `Records`/`detail`
  payload.
- **Cloudflare Workers env bindings (EP-18.6)**: `costorahWorker` reads
  exactly two binding values (`COSTORAH_API_KEY`/`COSTORAH_ENDPOINT`, or
  their configured overrides) from the `env` object — it never
  enumerates or logs the full `env` object, which may contain other
  secrets a Worker is bound to.
- **Task arguments in the Celery integration (EP-18.5)**: `task_failure`'s
  signal payload includes the task's original `args`/`kwargs` —
  `CostorahCelery` deliberately never reads them. Retry reasons are
  logged by exception class name only (`type(reason).__name__`), never
  `str(reason)`, since a custom retry exception could embed argument
  values in its message.
- **Authenticated user identity in the Django integration (EP-18.5)**:
  `CostorahMiddleware` captures the authenticated user's **ID only**
  (`request.user.pk`, read only when `request.user.is_authenticated` is
  `True`) — never the username, email, or any other field from the user
  object. Apps without `AuthenticationMiddleware` installed simply get
  no `user_id` field (accessed via `getattr`/a guarded `AttributeError`
  catch, never an error).

## Ambient request context (EP-18.4, extended EP-18.5)

The `costorah.context`/`context.ts` modules attach ambient metadata
(`request_context`/`requestContext`) to usage events during a request
(or, for Celery, during a task's execution). This is opt-in (only
populated when a framework integration is in use) and only ever
contains what the integration explicitly sets — request/task ID, path
or task name, method or queue/worker, organization ID, and (Django only)
user ID. It cannot capture arbitrary request data (headers, body, query
string) or task data (arguments, return value) because nothing in any
integration reads those into the context in the first place.

## Dependency audit

**Python** (`sdk/python/pyproject.toml`): one runtime dependency,
`httpx>=0.25` — a widely-used, actively maintained HTTP client with no
known critical advisories as of this review. Dev-only dependencies
(pytest, ruff, mypy, provider SDKs, fastapi, and — as of EP-18.5 —
flask/django/celery, needed only to run the framework integration test
suite) never ship in the published package; `costorah.integrations.*`
imports each framework lazily inside its own module, raising a clear
`ImportError` if it isn't installed, rather than requiring it.

**JavaScript** (`sdk/javascript/package.json`): **zero runtime
dependencies** (verified — no `dependencies` key in `package.json`;
Node's built-in `fetch`, `zlib`, `fs/promises`, and `async_hooks` cover
everything the reliability layer and framework integrations need). This
was a deliberate design constraint through EP-18.3/EP-18.4 specifically
to keep the security/supply-chain surface minimal — see
`RELIABILITY.md`'s note on why the persistent queue doesn't use LevelDB.

**The one exception (EP-18.6, `@costorah/sdk/nest`)**: `@nestjs/common`,
`@nestjs/core`, and `rxjs` are declared as `peerDependencies` (with
`peerDependenciesMeta` marking all three optional) — never bundled into
`dist/`, and `tsup.config.ts` explicitly marks them `external`
(verified: `grep '@nestjs\|rxjs' dist/nest/index.js` shows `import`
statements, not inlined code). This means: (1) a consumer who never
imports `@costorah/sdk/nest` never installs or ships these packages at
all — the main `@costorah/sdk` entry point's zero-dependency guarantee
is untouched; (2) a consumer who *does* use the NestJS integration runs
whatever NestJS/RxJS version *they* installed, not a version pinned at
this SDK's build time — this SDK never controls or vendors that
dependency's supply chain, the consumer's own `package-lock.json` does.
This was a deliberate, necessary exception (see `NESTJS.md`): real Nest
decorators must be genuine runtime imports for Nest's reflection-based
DI to recognize the resulting classes — there's no structural-typing
equivalent for a decorator-based framework the way `express.ts`/
`node.ts` avoid an Express/Node dependency.

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
- **Deno-specific security review (EP-18.6)**: since Deno wasn't
  available to test in this EP's environment (see `DENO.md`), no
  Deno-specific runtime behavior (e.g. its permission model interacting
  with this SDK's `fetch` calls) was verified — only assessed by code
  review.
- **NestJS peer-dependency supply chain**: this review does not audit
  `@nestjs/common`/`@nestjs/core`/`rxjs` themselves (they're peer
  dependencies a consumer supplies, not something this SDK vendors or
  controls the version of — see the dependency audit section above).
