# Costorah — Production Release Checklist

Produced by EP-26.0.3 ("Beta Readiness, Production Hardening & Real Provider Validation"). This is a living checklist, not a one-time artifact — re-run the relevant sections before every beta/production deploy. Every item below reflects the actual, verified state of this repository as of EP-26.0.3, not an aspiration; see CLAUDE.md's EP-26.0.3 section for the full validation methodology and evidence behind each checkmark.

**No live provider credentials, live Postgres, live Redis, or live Resend account were available in the sandbox this checklist was produced in.** Every item marked ✅ below was verified by direct source-code inspection and/or the existing hermetic test suite (1983+ backend tests, 298 frontend tests, all passing) — not by exercising a live deployment. Items that specifically require a live environment to confirm are marked 🟡 and called out explicitly. Do not treat this document as a substitute for a real staging-environment smoke test before the first real beta invite goes out.

---

## 1. Infrastructure

| Item | Status | Notes |
|---|---|---|
| FastAPI backend, `uvicorn`-served | ✅ | `app/main.py`, lifespan-managed via `AppContainer` |
| PostgreSQL (Neon) | 🟡 Config present, not live-tested | `DATABASE_URL` in `backend/.env` is a placeholder in this sandbox (`<YOUR_NEON_HOST>`) — must be a real Neon connection string before deploy |
| Redis | 🟡 Config present, not live-tested | Backs rate limiting (EP-24.4), the realtime event bus (EP-19.1), and the scheduler's cross-process lock (EP-23.4) — all three have documented, tested fallback behavior when Redis is unreachable (never a hard failure, see §7 Security below) |
| Dashboard SPA (Vite) | ✅ | `apps/dashboard`, builds clean (`vite build`) |
| Website SSR (TanStack Start / Nitro, Cloudflare Worker target) | ✅ | `apps/website`, builds clean, all 13 routes verified (§10 of CLAUDE.md) |
| Deployment configs present | ✅ | `deployment/docker`, `deployment/kubernetes`, `deployment/terraform`, `deployment/nginx`, `deployment/monitoring` — pre-existing, not modified by this EP |
| Health/readiness endpoints | ✅ | `GET /health` (liveness, always 200, inspects `status` field), `GET /ready` (load-balancer gating) — both check Postgres + Redis (`app/api/v1/health.py`) |
| Prometheus metrics | ✅ | `/metrics`-style rendering for alerts (`app/alerts/metrics.py`) and realtime (`app/realtime/metrics.py`), wired into the health module |

## 2. Database

| Item | Status | Notes |
|---|---|---|
| Alembic migration chain is single-headed, no branches | ✅ | Verified directly this EP: 21 migrations, one head (`c9d0e1f2a3b4`, EP-25.3's `email_delivery_events`), no orphan branches |
| Migration chain applies cleanly from scratch | 🟡 Not re-verified this EP | Verified against a real local Postgres in multiple prior EPs (EP-25.3, EP-24.5, EP-22.1) — re-run `alembic upgrade head` against the actual production Neon instance before first deploy, not just trust this checklist |
| Soft-delete convention (DP-7) applied consistently | ✅ | Every resource (`Organization`, `Project`, `ProviderConnection`, `OrganizationApiKey`, `Budget`, `User`) — confirmed across EP-18–EP-25 |
| No destructive migrations pending | ✅ | Every migration in the chain is additive (new tables/columns, nullable or defaulted) — confirmed by the chain's own EP history in CLAUDE.md §2 |
| `cryptography` runtime dependency declared | ✅ | Fixed in EP-22.1 (§15) — a real production incident (`ModuleNotFoundError` on Render) that this checklist exists partly to prevent from recurring silently |

## 3. Authentication

| Item | Status | Notes |
|---|---|---|
| Password registration + login | ✅ | Session cookie + bearer-token dual issuance (EP-21.2, §6) |
| Email verification enforced on login | ✅ | Fixed in EP-24.4.1 (§26) — a real bypass was found and closed; re-confirmed unregressed by the full test suite this EP |
| Google OAuth (Authorization Code + PKCE) | ✅ | State/CSRF/nonce validation, auto-linking by verified email (EP-24.5, §25) |
| Set-password flow for Google-only accounts | ✅ | Mandatory first-login gate, closes the "Google user never sets a password" bug (EP-24.6.1, §28) |
| Forgot/reset password | ✅ | Anti-enumeration (identical response regardless of account existence), one-time tokens, session-wide revocation on reset (EP-05, EP-24.4) |
| Logout / session refresh | ✅ | httpOnly cookie + memory-only access token, refresh-on-reload flow (§6) |
| Organization invitations (accept/decline/cancel/resend) | ✅ | 7-day expiring single-use token, email-match enforcement on accept (EP-24.6, §27) |
| Personal vs. Business workspace creation | ✅ | One workspace-creation code path (`_create_workspace`), reused for both (EP-25.1/EP-25.2, §29/§30) |
| Account deletion | ✅ | Blocks deletion while still OWNER of a shared workspace; cascades soft-deletes to owned resources (EP-22.2/EP-25.1) |
| Workspace deletion | ✅ | Type-to-confirm UI hardening + impact summary (EP-25.3, §31) |
| No known auth bypasses | ✅ | Re-confirmed this EP by re-reading `AuthService.login()`/`register()`/`login_or_register_with_google()` directly — the only two session-issuing code paths that don't require prior verification are `register()` (deliberate, documented) and Google OAuth (deliberate, documented — Google already verified the email) |

## 4. Providers

| Provider | Connect/Validate | Model Discovery | Historical Usage | Status |
|---|---|---|---|---|
| OpenAI | ✅ Live | ✅ Live | ✅ Real | Production-ready |
| Anthropic | ✅ Live | ✅ Live | ✅ Real (requires Admin-scoped key) | Production-ready |
| Google Gemini (AI Studio) | ✅ Live | ✅ Live, paginated | ⬜ Unavailable (platform limitation) | Ready — honest zero-usage by design |
| OpenRouter | ✅ Live | ✅ Live | 🟡 Real, credential-permission unconfirmed against a live account | Ready — see Known Limitations |
| Azure OpenAI | ✅ Live | 🟡 Static list, not live (EP-26.0.2.1 finding) | ⬜ Unavailable (platform limitation) | Ready — model list is a known gap |
| Grok (xAI) | ✅ Live | 🟡 Static list, not live (EP-26.0.2.1 finding) | ⬜ Unavailable (platform limitation) | Ready — model list is a known gap |
| Ollama | ✅ Live (reachability) | ✅ Live | ⬜ N/A (free/local, no billing) | Ready |

Every provider, without exception, goes through the identical `ProviderSyncService` → `UsageCollectionService` pipeline, the identical `EncryptionService`/`ProviderCredentialService`/`ProviderValidator` credential path, and renders through the identical dashboard/analytics/budget/alert surfaces — re-confirmed by direct source-code audit in EP-26.0.2.1 and EP-26.0.3. See CLAUDE.md's EP-26.0.2.1 and EP-26.0.3 sections for the full comparison table and per-provider validation checklist.

**No live provider credential of any kind was available in this sandbox at any point in EP-26.0.2.1 or EP-26.0.3.** Every ✅ above reflects hermetic tests against realistic mocked HTTP responses, cross-checked against the provider's own published API documentation — not a first-party response this session directly observed. **This is the single most important gap to close before external beta users connect real accounts**: have someone with real OpenAI/Anthropic/Google/OpenRouter credentials walk through Connect → Validate → Sync → Disconnect once against the actual deployed backend before broad beta access.

## 5. Scheduler

| Item | Status | Notes |
|---|---|---|
| Automatic background sync | ✅ | `UsageSyncScheduler`, per-org interval (5m/15m/1h/6h/24h), EP-23.4 |
| Manual "Sync now" / "Sync all" | ✅ | EP-23.3 |
| Retry / exponential backoff | ✅ | `ProviderHttpClient` + `ExponentialRetryPolicy`, reused unchanged by every provider and every scheduler dispatch (EP-06/EP-07/EP-19/EP-20) |
| Checkpoint recovery | ✅ | `UsageCollectionCheckpoint`, resumes from `last_collected_at`, never re-fetches a provider's entire history (EP-08/EP-23.3) |
| Due-detection is stateless across restarts | ✅ | Re-derived from the `UsageCollectionRun` table every tick, not from in-memory state — a deployment restart cannot silently skip or double-sync an organization (EP-23.4, verified by direct code read) |
| No duplicate sync jobs | ✅ | Two-layer guard: in-process `_running_org_ids` set + cross-process Redis lock (`scheduler:lock:org:{id}`, `SET NX EX`) — Redis-unreachable degrades to the in-process guard only, never blocks sync entirely (EP-23.4) |
| Sync history / status badges | ✅ | `SchedulerStatusResponse`/`SchedulerJobItem` API, `AutoSyncStatusSection` UI (EP-23.4) |
| Budget evaluation piggybacks on sync | ✅ | `BudgetEvaluationService.evaluate_and_alert()` runs after every successful sync (scheduled or manual), never a second scheduler (EP-24.2) |

## 6. Dashboard

| Page | Status | Notes |
|---|---|---|
| Overview | ✅ | 8 KPI cards, `GettingStartedBanner`/`DashboardStateHero` 4-state empty-state machine, Sync Activity, budget summary cards |
| Analytics | ✅ | Filters (project/provider/model), Token Trend, Usage Heatmap, Project Spend ranking, CSV export, live refresh |
| Projects | ✅ | Real CRUD (EP-23), analytics + management views coexist |
| Providers/Connections | ✅ | Real CRUD + encrypted credentials + live validation + sync status (EP-22/EP-23.3/EP-26.0.1/EP-26.0.2) |
| Budgets | ✅ | Real CRUD, multi-threshold alerts, forecast (linear extrapolation, documented as such) |
| Alert Center | ✅ | Real filtering/search, full lifecycle actions (acknowledge/resolve/dismiss/reopen) |
| Settings | ✅ | Profile, Workspace, Password, Preferences, API Keys, Danger Zone — all backend-persisted, no placeholder UI (EP-22.2) |
| API Keys | ✅ | Real create/rename/revoke, shared component between standalone page and Settings tab |
| Members | ✅ | Real invite/accept/role-change/remove, ownership-safety guards (EP-24.6/EP-24) |
| Invitations | ✅ | Real lifecycle, email delivery via Resend (EP-24.6) |
| Empty states | ✅ | Every zero-data page renders a specific, actionable message — none render a blank/confusing screen (audited in EP-26.0.2.1 Part 7) |
| Loading states | ✅ | Every mutation shows a spinner while pending |
| Dark mode / 3-theme system | ✅ | `neon-cyber`/`professional-light`/`professional-dark`, pre-render blocking script avoids FOUC |
| Responsive layouts | 🟡 Not re-verified this EP | Documented as built-in from the original component library; no dedicated responsive-breakpoint audit has been performed in any EP to date — flagged as an open item, not silently assumed |

## 7. Budgets

| Item | Status |
|---|---|
| Create / edit / delete | ✅ |
| Scope: organization / project / provider / model | ✅ |
| Multiple independent thresholds per budget | ✅ |
| Linear forecast (projected period spend, remaining daily allowance) | ✅ — explicitly documented as linear extrapolation, not ML, per the original spec's own instruction |
| Evaluated after every sync (scheduled + manual) | ✅ |
| Dashboard summary (Budget Remaining, Active Alerts, Projected EOM Spend) | ✅ |

## 8. Alerts

| Item | Status |
|---|---|
| Budget threshold / budget exceeded firing | ✅ |
| Deduplication (per budget + period + threshold) | ✅ — re-crossing an already-open threshold folds into the same `Alert` row (`occurrence_count` increments), never a duplicate |
| Severity banding (INFO → CRITICAL) | ✅ |
| Dashboard delivery (bell + Alert Center) | ✅ |
| Email delivery for alerts | ⬜ Not built | Explicitly out of scope per EP-24.2's own disclosed limitation — only the dashboard channel exists; the architecture is designed so email/Slack/webhook channels plug in later without touching `BudgetEvaluationService` (documented, not yet implemented) |

## 9. Email (Resend)

| Item | Status | Notes |
|---|---|---|
| Registration / verification email | ✅ | EP-24.4 |
| Forgot password email | ✅ | EP-24.4 |
| Organization invitation email | ✅ | EP-24.6 |
| Invitation accepted / cancelled notifications | ✅ | EP-24.6 |
| Delivery-event webhook (bounce/complaint/delivered) | ✅ | Svix-signature-verified receiver, `email_delivery_events` table (EP-25.3, §31 Part 5) |
| Templates: responsive, dark-mode-aware, branded | ✅ | Shared `_layout()`/`_button()` helpers, no placeholder content in any template (verified via `TestEmailTemplateRenderer` since EP-24.4) |
| No secrets in email logs | ✅ | `ResendEmailProvider` logs only recipient domain, subject, provider message id — never the API key or full address in warning-level logs |
| Live Resend account exercised | 🟡 Not verified | No `RESEND_API_KEY` configured in this sandbox — every email test is hermetic (`httpx.MockTransport`); confirm real delivery against a live Resend account before beta |

## 10. Security

| Item | Status | Notes |
|---|---|---|
| Encryption at rest (`EncryptionService`, Fernet + PBKDF2) | ✅ | EP-22, key-rotation-ready via `APP_SECRET_KEY_PREVIOUS` |
| API key masking in every response | ✅ | Never a decrypted secret leaves the process |
| JWT (HS256, `jwt_secret`) | ✅ | Access token memory-only, refresh token hashed at rest |
| httpOnly session cookies | ✅ | `SameSite=Lax`, `.costorah.com`-scoped in production |
| Google OAuth CSRF/state/nonce | ✅ | Signed JWT state, double-submit cookie, constant-time comparison (EP-24.5) |
| Replay protection | ✅ | One-time tokens (verification/reset/invitation), Google's own one-time authorization codes |
| Rate limiting (login, email resend, invitations) | ✅ | Redis-backed sliding window with documented in-memory-per-process fallback |
| RBAC — Personal accounts | ✅ | Structural OWNER-holds-everything bypass, no coded special case (EP-25.1) |
| RBAC — Business accounts | ✅ | Role hierarchy re-audited twice (EP-24 §18, EP-25.2/EP-25.3 §30/§31), one real gap found and fixed each time |
| Audit logging (structured, no secrets) | ✅ | `app/auth/audit.py` + `app/organizations/audit.py`, spot-checked this EP — no key/token/password value ever appears as a log field in the files checked |
| No secret ever logged | ✅ (spot-checked this EP) | Verified directly this EP via grep across `encryption.py`, `google_oauth.py`, `resend_provider.py` — no match for a key/token/password/secret value bound as a structlog field |
| Production-mode config enforcement | ✅ | `_enforce_secret_in_production`, `_enforce_email_config_in_production` validators refuse to boot with dev defaults in `APP_ENV=production` |

## 11. Performance

| Item | Status | Notes |
|---|---|---|
| No new duplicate-query regressions found this EP | ✅ | Re-audited `Connections.tsx`/`Overview.tsx`/`Analytics.tsx` — no new duplication beyond the already-documented, already-accepted independent 20s scheduler-status polling on two pages |
| React Query caching | ✅ | Consistent `["resource", orgId, ...]` key convention across every hook, shared cache confirmed across page boundaries (e.g. Connections page and Onboarding wizard share `["provider-connections", orgId]`) |
| Database query indexing | ✅ | Every dashboard/analytics aggregate filters on already-indexed `(org, usage_date)`/`(org, provider, usage_date)`/`(org, project_id, usage_date)`/`(org, model, usage_date)` columns — confirmed across EP-24.1/EP-24.2's own performance sections |
| Live API latency under real load | 🟡 Not measured | No live deployment or load-testing tool was available in this sandbox — this is a real, open gap, not a checked box |
| Large-payload handling (model catalogs, pagination) | ✅ | Google's live catalog is bounded (`_MAX_MODEL_CATALOG_PAGES = 10`); every cursor-paginated list endpoint has a bounded default page size |

## 12. Testing

| Item | Status |
|---|---|
| Backend: `pytest` | ✅ 1983 passed, 30 skipped (DB-gated integration tests) |
| Backend: `ruff check` | ✅ clean |
| Backend: `black --check` | ✅ clean |
| Backend: `mypy app` | ✅ clean (204 source files) |
| Frontend: `vitest run` | ✅ 298 passed |
| Frontend: `eslint --max-warnings 0` | ✅ clean |
| Frontend: `tsc -b` | ✅ clean |
| Frontend: `vite build` (production) | ✅ clean |
| Website: full suite + build | ✅ (unaffected by this EP; re-run as regression per standing convention) |
| Live integration tests against real Postgres | 🟡 Not run this session | Gated behind `DATABASE_URL` — this sandbox has none configured; these tests have been run against real Postgres in several prior EPs (documented per-EP), not in this one |

## 13. Documentation

| Item | Status |
|---|---|
| `CLAUDE.md` — architecture reference, every EP documented | ✅ |
| `STARTUP.md` — provider onboarding, production deployment guide | ✅ (this EP adds §18 Production Deployment Guide) |
| `RELEASE_CHECKLIST.md` — this document | ✅ (new, this EP) |
| Per-provider limitations disclosed honestly, no fabricated capability | ✅ |

## 14. Deployment

| Item | Status | Notes |
|---|---|---|
| Backend deploy target | Render (documented, per §10 of CLAUDE.md and `backend/.env.example`) | Confirm `pip install -e "."` (no `dev` extra) matches production dependencies — this exact check caught EP-22.1's real incident |
| Website deploy target | Cloudflare Worker (Nitro `cloudflare-module` preset) | Not Cloudflare Pages — confirmed distinct requirement in §10 |
| Dashboard deploy target | Static SPA build (Render, per §6) | |
| Monorepo build rule | `pnpm --filter <package>... build` (note the `...`) | Its omission was the direct cause of a real documented incident (§2) |

---

## Known Limitations (carried forward, disclosed, not hidden)

1. **No live provider credential has ever been used to validate this platform**, for any of the 7 providers, in any EP. Every validation to date is hermetic (mocked HTTP against realistic, researched response shapes). This is the single highest-priority item before broad beta access.
2. **Azure OpenAI and Grok have static, not live, model catalogs** — found in EP-26.0.2.1, not yet fixed (deliberately out of scope for a validation-only EP).
3. **OpenRouter's usage-import credential-permission requirement is unconfirmed** against a real account (EP-26.0.1).
4. **Google's live model-catalog field mapping is unconfirmed** against a real AI Studio response (EP-26.0.2).
5. **No alert email/Slack/webhook delivery** — dashboard-only today, architecture ready for more channels.
6. **No live load-testing has been performed** — API latency, dashboard render performance, and scheduler throughput under real concurrent load are unmeasured.
7. **No self-service "add a password" flow** for a Google-only account beyond the mandatory first-login gate.
8. **Responsive-layout breakpoints have never been dedicated-audited** — built on an existing component library assumed responsive, never specifically re-verified.
9. **`DATABASE_URL` in this sandbox is a placeholder** — every "run the full test suite" claim in this document is against a hermetic, mocked-DB test suite, not a live Postgres instance, except where a specific prior EP is cited as having run one.

## Go / No-Go Decision

**Recommendation: GO for a limited, closely-monitored external beta — NOT a general/public launch.**

Rationale: every workflow this checklist covers has real, working, tested code behind it — no fabricated functionality was found anywhere in this audit, and the platform's own standing convention (disclosed limitations over fake features) has held up under this EP's direct source-code re-verification. The gating condition for "GO" is narrow and specific: **before the first external beta user connects a real provider account, have someone manually walk through Connect → Validate → Sync → view real usage on the dashboard against at least OpenAI or Anthropic (the two providers with real historical usage import) on the actual deployed environment.** Nothing in this codebase's architecture is expected to behave differently in production than in the hermetic test suite — every provider adapter, every service, every repository is the same code path regardless of environment — but "expected to work" and "confirmed working against a live account" are not the same claim, and this document is explicit about which one it can honestly make today.

Do not go to a **general/public** launch until: (1) at least one live-account smoke test per provider has been performed against the real deployed backend, (2) Redis and Resend are confirmed live and correctly configured in the production environment (not just present in `.env.example`), and (3) a basic load/latency check has been run against the real deployment at least once.
