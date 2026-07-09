# CLAUDE.md — Costorah Engineering Memory

This is the permanent architecture reference for Costorah (AI FinOps). It records what exists today, the target unified-product architecture, and the roadmap to get there. Keep it current as each EP below lands — this document, not any single PR description, is the source of truth for "why is it built this way."

---

## 0. ADR-006 — Multi-Subdomain Architecture (FINALIZED)

**Status: Decided. Do not redesign this architecture in future EPs unless explicitly requested.**

Costorah uses a multi-subdomain architecture, not a single-origin or path-prefixed one.

**Primary domains:**
- `https://costorah.com` — public marketing website. Owns: Landing page, Features, Pricing, Security, Enterprise, Documentation, Blog, Contact, Login, Register.
- `https://app.costorah.com` — authenticated SaaS application. Owns: Dashboard, Personal Workspace, Organization Workspace, Projects, Provider Connections, Usage, Analytics, Costs, Alerts, API Keys, Billing, Settings.

**Future reserved domains** (not built yet, names reserved so routing/cert/DNS decisions elsewhere don't collide with them): `https://docs.costorah.com`, `https://status.costorah.com`, `https://api.costorah.com`.

**Authentication is one system, not two.** There is exactly one user-account system (the backend's existing `User`/`Organization`/`Membership` tables). The website never has its own parallel account store — it authenticates directly against the same backend the dashboard uses. The flow: visitor on `costorah.com` clicks Login or Get Started → authenticates against the backend → backend sets a session → browser is redirected to `app.costorah.com` → the session is already valid there because the session cookie is scoped to the shared parent domain `.costorah.com`. See §6 for the concrete mechanism.

**Why subdomains over path-prefixing**: the website is SSR (TanStack Start/Nitro) and the dashboard is a client-rendered SPA (Vite) — two different rendering models. A shared parent domain is what makes the cookie-based session in §6 work without any cross-origin token-passing; a path-prefix would additionally require a reverse proxy routing by path between two differently-deployed runtimes, for no benefit over the subdomain split. Both apps remain independently deployable (§2, §9).

---

## 1. Product Shape

Costorah is an AI-cost-observability platform: customers connect their AI provider accounts (OpenAI, Anthropic, etc.) or integrate an SDK, and Costorah ingests usage/cost data and surfaces it through dashboards, analytics, and budget alerts.

The product is now **one monorepo, two frontends, moving toward one seamless experience** (ADR-006, §0):
- `apps/website` — public marketing site (`costorah.com`), migrated from the standalone `costorah-ai-guide-main` Lovable repo.
- `apps/dashboard` — authenticated product (`app.costorah.com`), moved from this repo's former `frontend/`.

Both now live in one pnpm workspace alongside `backend/` (FastAPI) and `packages/*`. The physical merge (EP-21 milestones 1–3) and registration/auth unification (EP-21.2, milestone 4) are done and verified; the remaining EP-21 work is shadcn/ui component de-duplication and website CI/Turborepo (milestones 5–6) — see §9.

---

## 2. Repository Structure

### Current (as of EP-21 milestone 3 — implemented, not aspirational)
```
AI-FinOps/                  (pnpm workspace: apps/* + packages/*)
├── apps/
│   ├── dashboard/            @costorah/dashboard — Vite SPA, moved from frontend/ (git-tracked rename, history preserved)
│   └── website/               @costorah/website — TanStack Start SSR, imported from costorah-ai-guide-main
│                               (flat import, not git-subtree: the Lovable export had no .git/ at all — no history existed to preserve)
├── backend/                   FastAPI monolith, unchanged
├── packages/
│   ├── shared-ui/              @costorah/shared-ui — seeded: cn() is now defined once here, re-exported
│   │                           from both apps' existing "@/lib/utils" / "@/utils" entry points.
│   │                           shadcn/ui primitive adoption + design-token unification still open (EP-26).
│   ├── shared-types/, shared-config/, api-contracts/, event-schema/, error-codes/
│   │                           all renamed @ai-finops/* -> @costorah/* (done)
├── sdk/                       @costorah/sdk (Python + JS) — same scope as everything else now
├── provider-adapters/, monitoring-agent/, docs/, deployment/, ...
```

**Package naming**: done. Every internal workspace package (including the dashboard and website themselves) is `@costorah/*`, matching the SDK. No more `@ai-finops/*` scope anywhere in the repo.

**A note for anyone restructuring directories in this repo further**: the root `.gitignore`'s Python-section `lib/` pattern (line 13) silently matches *any* path ending in `lib/`, including `apps/*/src/lib/`. Each app under `apps/` needs its own `!apps/<name>/src/lib/` negation — this was already true for `apps/dashboard` but was missing for `apps/website` until EP-21 milestone 3 caught it (a fresh clone was silently missing 4 required source files). Verify with `git ls-files apps/<name> | wc -l` against `find apps/<name> -type f | wc -l` (excluding `node_modules`/build output) after any directory move.

### Not yet done (see §9 for the honest remaining list)
- `packages/shared-utils` (formatting helpers, `PROVIDER_COLORS`) — not created yet.
- shadcn/ui adoption in `apps/dashboard` in place of its hand-rolled primitives — not started; `packages/shared-ui` currently only exports `cn()`.
- Turborepo — not introduced; still plain `pnpm --recursive`/`--filter`.
- Website CI (`apps/website` has no lint/build/test job in `.github/workflows/ci.yml` yet — only the dashboard's jobs were updated to the new path).

### Monorepo Build Rule

All Cloudflare Pages, Vercel, Netlify, CI, and local production builds for workspace applications must use:

```
pnpm --filter <package>... build
```

Never use:

```
pnpm --filter <package> build
```

Packages such as `@costorah/shared-ui`, `@costorah/shared-types`, and `@costorah/api-contracts` ship no committed build output (`dist/` is gitignored by design — see the Node section of `.gitignore`) and must be built before their consumers. The `...` selector tells pnpm to include the target package's full workspace dependency graph and build it in topological order (dependencies first); the bare form without `...` builds only the named package and silently skips its unbuilt workspace dependencies, which is what produced the `TS2307: Cannot find module '@costorah/shared-ui'` Cloudflare Pages failure on `apps/website` — the platform's build command was scoped to `apps/website` alone, so `packages/shared-ui`'s `tsc --build` step never ran and `dist/index.d.ts` never existed in that build environment.

---

## 3. Website Architecture

Location: `apps/website/` (imported from the standalone `costorah-ai-guide-main` Lovable export — see §2 and §8 milestone 2).

- **Framework**: TanStack Start — SSR, file-based routing (`src/routes/*.tsx`), root shell `__root.tsx`. Not a static site; requires a running SSR server (Nitro, Cloudflare-targeted by its build config).
- **Styling**: Tailwind v4, CSS-first config (no `tailwind.config.*` — tokens live in `src/styles.css` via `@theme inline`). OKLCH color space, dark-only palette (no light mode built). Brand color `#14D9D3` → `#7AF7E8` (teal → mint).
- **Components**: shadcn/ui (Radix-based) fully installed (38 primitives in `src/components/ui/`) but **currently unused** — pages use raw Tailwind instead. Custom shell components: `SiteLayout`, `SiteNav`, `SiteFooter`, `PageHeader`, `StubPage`, inline-SVG `LogoMark`.
- **Fonts**: Inter (body), Space Grotesk (display), JetBrains Mono (code) — all via Google Fonts `<link>` tags. Same families as the dashboard, different loading mechanism (link tags vs. CSS `@import`).
- **Routes**: 13 total. Only 4 have real content — `/` (landing page), `/contact`, `/login`, `/signup`. The other 9 (`about`, `blog`, `developers`, `docs`, `features`, `pricing`, `security`, `privacy`, `terms`) are `StubPage` placeholders with no unique copy.
- **Backend integration**: real, as of EP-21.2 (§6) — `/signup` and `/login` call `POST /v1/auth/register` / `/login` via `src/lib/api.ts`. `/contact` is still a static form (`preventDefault()` only, no endpoint exists to submit to).
- **Deployment**: see §10 — deployed to Cloudflare via Nitro's `cloudflare-module` preset (a Cloudflare **Worker** with static assets, built with `wrangler deploy`/Workers Builds), not a plain static site and not Cloudflare Pages' static-only mode. No Dockerfile/vercel.json; `wrangler.json` is generated at build time into `.output/server/`, not committed (build artifact).

## 4. Dashboard Architecture

Location: `apps/dashboard/` (moved from this repo's former `frontend/` — see §2 and §8 milestone 1).

- **Framework**: Vite SPA, React 18.3, React Router v6 (`BrowserRouter`, classic `<Routes>`), served at root `/` with no base path.
- **Styling**: Tailwind v3.4 (TS config file). No shadcn/ui or Radix — every primitive (`Dialog`, `Popover`, `Avatar`, `ConfirmDialog`, `MetricCard`, `ToastContainer`) is hand-rolled, using Framer Motion for animation.
- **Theming**: a **3-theme system** — `neon-cyber` (default), `professional-light`, `professional-dark` — switched via `data-theme` attribute on `<html>`, controlled by `useThemeStore` (Zustand, manual `localStorage` write, not the `persist` middleware). An inline blocking `<script>` in `index.html` sets the initial theme pre-render to avoid FOUC. RGB-triplet CSS custom properties, consumed as `rgb(var(--x) / alpha)`.
- **Fonts**: Inter + Space Grotesk via CSS `@import` in `index.css`. JetBrains Mono is declared in the Tailwind config but **never actually loaded** — a latent bug to fix during font unification.
- **State**: Zustand, 8 stores (`auth`, `org`, `theme`, `ui`, `notifications`, `onboarding`, `profile`, `toast`).
- **Data fetching**: TanStack Query v5.
- **Routes** (all lazy-loaded, each wrapped in its own `ErrorBoundary`): 20 `src/features/*.tsx` files. Public: `/login`, `/forgot-password`, `/reset-password`, `/verify-email`. Protected, standalone (behind `ProtectedRoute` only — no `AppLayout` chrome): `/onboarding` (EP-21.3, see §11). Protected (behind `ProtectedRoute` + an org-membership `AuthGuard`): `/dashboard` (+ `/analytics`, `/providers`, `/models`, `/projects`, `/organization`, `/pricing`), `/users`, `/rbac`, `/api-keys`, `/connections`, `/audit-logs` (placeholder), `/settings`, `/support`.
- **Known gaps carried into this migration** (from the prior product-completeness audit): `Settings.tsx` doesn't persist anything to the backend despite a full save UI; `/audit-logs` is a nav-reachable placeholder.

## 5. Design System

The two apps currently run **two different token systems**. Unification plan (full detail and rationale in the migration plan doc):

| Category | Website (today) | Dashboard (today) | Target |
|---|---|---|---|
| Fonts | Inter, Space Grotesk, JetBrains Mono — all loaded, Google Fonts `<link>` | Inter, Space Grotesk loaded; JetBrains Mono declared but never loaded | Shared, self-hosted font files in `packages/shared-ui/tokens/` |
| Color space | OKLCH | RGB triplets | OKLCH (Tailwind v4's native format) |
| Brand color | `#14D9D3` / `#7AF7E8` | separate teal `--color-brand` + legacy indigo `--color-primary` | One canonical brand teal, one value |
| Theming model | dark-only, no switcher | 3-theme (`neon-cyber`/`professional-light`/`professional-dark`) via `data-theme` | Keep the dashboard's `data-theme` mechanism; website's current palette becomes the `neon-cyber` seed; don't force a switcher onto the website unless product wants one |
| Radius scale | base 14px | `card` 12px / `card-lg` 20px / `card-xl` 28px | Dashboard's scale (exercised across 19 real screens) |
| Component primitives | shadcn/ui installed, unused | hand-rolled, no shadcn/Radix | Adopt shadcn/ui as the one shared layer in `packages/shared-ui`; migrate dashboard screens off hand-rolled primitives incrementally |
| Toasts | shadcn `sonner` installed, unused | bespoke `ToastContainer` + `toast.ts` store | `sonner`, shared |
| Provider brand colors | none yet | hardcoded hex constants (OpenAI green, Anthropic tan, etc.) | Move to `packages/shared-utils` as `PROVIDER_COLORS` |

---

## 6. Authentication & Session Model

### Current (as of EP-21.2 — complete)
- **Backend issues both mechanisms on every browser-session response** (`POST /v1/auth/register`, `/login`, `/refresh`): the original JSON token body (`TokenResponse`) **and** httpOnly `SameSite=Lax` cookies (`costorah_access_token`, `costorah_refresh_token` — `app/auth/cookies.py`). `GET /v1/auth/me` and every other authenticated endpoint accept either: `get_current_user` checks the `Authorization` header first, falls back to the cookie. This is deliberately additive, not a cutover — no existing client had to change.
- **Website**: `/signup` and `/login` (`apps/website/src/routes/signup.tsx`, `login.tsx`) call the real `POST /v1/auth/register` / `POST /v1/auth/login` via `apps/website/src/lib/api.ts` (`credentials: "include"`, zod validation matching the backend's field constraints exactly, inline error states for 409/401/429/network failure). No more static mockups.
- **Cross-origin handoff to the dashboard**: `apps/dashboard` is still Zustand bearer-token auth, not cookie-aware — see below. Rather than rearchitecting it, the website redirects to `app.costorah.com` with the token pair and user/workspace JSON base64-encoded in the URL **fragment** (`buildDashboardHandoffUrl()` in `apps/website/src/lib/api.ts`; e.g. `/onboarding#session=...`). Fragments are never sent to any server by the browser, so this carries no more exposure than the existing bearer-token-in-JS model — it's the same technique OAuth's implicit flow used for that exact property. `apps/dashboard/src/lib/consumeSessionHandoff.ts` runs once before first render (wired into `main.tsx`), feeds the payload into the dashboard's existing `setLogin()`/`setOrganization()` calls unchanged, then strips the fragment via `history.replaceState`. This bridge is temporary and self-documents its own removal condition in its file header.
- **Browser session (dashboard)**: still bearer JWT via Zustand, exactly as before (`ProtectedRoute`'s `/v1/auth/refresh`-on-reload flow, `localStorage` refresh token only if "remember me"), now populated either by its own `/login` form or by the handoff above. Untouched and not required to migrate — the dashboard could adopt the cookie later (`credentials: "include"`) as a cleanup, not a blocker; doing so would also let the fragment-handoff bridge be deleted.
- **Cookie domain**: `settings.session_cookie_domain` (env `SESSION_COOKIE_DOMAIN`), `None` by default (host-only cookie — correct for local dev, since cookies aren't port-scoped). Set to `.costorah.com` in production so the cookie is valid on both `costorah.com` and `app.costorah.com`.
- **CORS**: `settings.api_cors_origins` (`app/config/settings.py`) allow-lists `https://costorah.com`, `https://www.costorah.com`, `https://app.costorah.com` (plus `localhost` dev ports and a pre-existing unrelated `op.0protocol.net` seed-data origin — see §10). `www.costorah.com` was missing until the §10 audit; a `fetch()` blocked by CORS throws a generic (non-`ApiError`) exception in `apps/website/src/lib/api.ts`, which the signup/login forms surface as "Could not reach the server." — indistinguishable in the UI from an actual network failure, so a missing allow-listed origin is easy to misdiagnose as a connectivity problem. `allow_credentials=True` is required (and set) alongside this list, since the website's fetches use `credentials: "include"`.
- **M2M / SDK**: unchanged — separate mechanism, Organization API Keys (`Authorization: Bearer costorah_live_...`), validated by `CurrentApiKey`/`RequireApiKeyPermission`. Not part of the browser-session cookie work; API keys and browser sessions remain distinct concerns.

### Remaining for full seamless handoff
1. `apps/dashboard`'s API client migrates from `Authorization: Bearer <token from Zustand>` to `credentials: "include"`, letting the cookie carry the session instead of JS-managed tokens. Not required today — the fragment handoff already gets a fresh registrant from the website into a working dashboard session — but is the natural cleanup that lets `consumeSessionHandoff.ts` and `buildDashboardHandoffUrl()` be deleted, and lets `apps/dashboard`'s own `Login.tsx` be retired in favor of the website's `/login`.

### Domain topology
`costorah.com` → website (SSR, Cloudflare). `app.costorah.com` → dashboard (static SPA build, same host as today — currently Render). Subdomain, not path-prefix, because the SSR/SPA split makes a shared reverse-proxy path-routing setup extra infrastructure for no benefit, and a shared parent domain is exactly what the cookie model above needs.

---

## 7. Workspace / Organization Architecture

**"Workspace" in the requested product flow = the existing `Organization` entity.** No second data model is introduced — this matches how Linear/Vercel/Notion model personal and team workspaces as the same underlying entity.

- **Personal workspace auto-creation**: ✅ done (EP-21.2). `POST /v1/auth/register` creates one `Organization` row (`is_personal=True`, named `"{display_name}'s Workspace"`, unique slug) with the new user as sole `OWNER` `Membership`, in the same transaction as the `User` row — `AuthService.register()`. There is still no *general-purpose* org-create endpoint (only this registration-time special case, plus the pre-existing `GET /v1/organizations` — list mine) — creating a second, non-personal team org is not yet possible via the API.
- **Renaming a workspace**: ✅ done (EP-21.3). `PATCH /v1/organizations/{org_id}` (`ORG_WRITE` permission — OWNER/ADMIN only) updates `name`; `slug` is intentionally not editable through this endpoint and never changes as a side effect of a rename.
- **Switching workspaces**: already implemented — `OrgSelector.tsx` + `useOrgStore` handle multi-org membership. Now has something real to switch *to* — the website's `/signup` creates the personal workspace and the session handoff (see §6) populates `useOrgStore` with it immediately, no manual step. Still nothing to switch to *beyond* that until general-purpose org creation exists.
- **Inviting members**: real and working (`POST /v1/organizations/{id}/members`) — but invite emails are never delivered, because **no outbound email transport exists anywhere in the platform**. The same gap silently breaks password-reset and verification emails. One transactional-email integration fixes all three.
- **Projects**: modeled (`Project` entity, repository) but **no CRUD API exists** — only used internally by usage ingestion to validate `project_id`.
- **Provider Connections**: modeled (`ProviderConnection` entity, repository) but **never wired to any router** — the only provider-related endpoints today (`/v1/providers/{provider}/test|models|info`) are a stateless connectivity probe against server-side environment-variable keys, not a customer-entered, persisted credential. This is the concrete blocker for the "Connect OpenAI / Connect Anthropic" onboarding steps being real rather than a demo.

---

## 8. Migration Roadmap

Dependency-ordered. Extends the roadmap from the prior product-completeness audit. Status reflects reality as of the last commit to this file, not aspiration — see §9 for exact verification evidence per item.

1. **EP-21 — Website + dashboard repository unification.** *(this initiative — in progress)*
   - ✅ **Milestone 1 — `apps/dashboard` restructure.** `frontend/` → `apps/dashboard` (git-tracked rename, history preserved), `@ai-finops/*` → `@costorah/*` scope across every package, `pnpm-workspace.yaml`/`docker-compose.yml`/CI/CODEOWNERS updated, broken `tsconfig` `extends` paths from the directory-depth change fixed. Verified: build/lint/typecheck/test (124 tests) all pass.
   - ✅ **Milestone 2 — `apps/website` import.** Imported as a flat single commit (source had no `.git/` — no history to preserve). Lovable-hosting-specific files removed (`bun.lock`, `bunfig.toml`, `.lovable/`, `AGENTS.md`); package renamed `@costorah/website`; 162 pre-existing prettier violations auto-fixed. Verified: builds unmodified inside the monorepo (Cloudflare-target Nitro SSR, all 13 routes).
   - ✅ **Milestone 3 — `packages/shared-ui` seeded.** `cn()` deduplicated (was byte-identical in both apps) into one implementation, re-exported from both apps' existing import paths. Caught and fixed a real bug in the process: the root `.gitignore` was silently excluding all of `apps/website/src/lib/` (4 files) from milestone 2's commit — a fresh clone would have been broken. Verified via an actual fresh `git clone` + install + build of all three packages, not just re-running in the existing working tree.
   - ✅ **Milestone 4 — EP-21.2 "Registration & Personal Workspace"** *(complete)*
     - ✅ **Backend.** `POST /v1/auth/register`, `GET /v1/auth/me`, httpOnly session cookies (`costorah_access_token`/`costorah_refresh_token`) on register/login/refresh, cleared on logout. `organizations.is_personal` column (migration `fe2f617c934d`) — a personal workspace is an `Organization` with `is_personal=True`, no new entity. `AuthService.register()` extends the existing service (shared `_issue_session()` helper with `login()`), reuses `hash_password`/`UserRepository`/`OrganizationRepository`/`MembershipRepository` — no parallel auth system. 16 new tests, full suite 1467 passed, ruff/mypy/black clean.
     - ✅ **Frontend — website.** `apps/website`'s `/signup` and `/login` routes call `POST /v1/auth/register` / `POST /v1/auth/login` for real (`apps/website/src/lib/api.ts`, `authSchemas.ts`), with loading/success/error states and duplicate-email (409) / bad-credentials (401) / rate-limit (429) handling. No more `preventDefault()`-only mockups. 14 new website tests.
     - ✅ **Frontend — dashboard onboarding.** `apps/dashboard/src/features/Onboarding.tsx`, a 5-step wizard (`Welcome → Connect AI Provider → Create First Project → Generate API Key → Open Dashboard`) at the new `/onboarding` route. Connect-Provider and Create-Project steps are honest placeholders (no CRUD API yet — EP-22/EP-23), matching `Placeholder.tsx`'s existing convention, not broken links. The API-key step is real, reusing the existing `createApiKey()` call from `ApiKeys.tsx`.
     - ✅ **Cross-origin session handoff.** Because `apps/dashboard` is still Zustand-bearer-token auth and the website is now cookie-only, `apps/website` redirects post-register/login to `app.costorah.com` with the session in the URL fragment (`buildDashboardHandoffUrl()`); `apps/dashboard/src/lib/consumeSessionHandoff.ts` consumes it once before first render into the existing `setLogin()`/`setOrganization()` calls, then strips the fragment. See §6 for the full rationale and removal condition. 6 new dashboard tests.
     - ⬜ **Dashboard auth migration** (optional cleanup, not an EP-21.2 blocker). `apps/dashboard`'s API client still attaches `Authorization: Bearer <token from Zustand>`; migrating it to `credentials: "include"` would let the fragment-handoff bridge and `apps/dashboard`'s own `Login.tsx` be retired in favor of the website's. Not started, not required — the acceptance criteria are met without it.
   - ⬜ **Milestone 5 — shadcn/ui adoption in `apps/dashboard`, full component de-duplication.** Not started — `packages/shared-ui` currently exports only `cn()`. This is the largest remaining piece of "no duplicate components remain" and should be sized as its own multi-PR effort, not a single milestone.
   - ⬜ **Milestone 6 — Website CI wiring, Turborepo, `packages/shared-utils`.** Not started.
2. **EP-21.3 — First-Time User Onboarding.** *(complete — see §11)* Replaced the EP-21.2-era `/onboarding` wizard's steps with the product-spec'd flow (Welcome → Workspace → Choose Provider → Product Tour → Finish), added real server-side completion persistence (`users.onboarding_completed_at`) so it only ever shows once, and a workspace-rename endpoint.
3. **EP-22 — Provider Connections (real, persisted).** Full CRUD API + UI for the already-modeled `ProviderConnection` entity. Not started. Onboarding Step 3 (§11) and the dashboard's `/connections` page both currently route around this gap rather than fake it.
4. **EP-23 — Projects CRUD.** Same treatment for `Project`. Not started.
5. **EP-24 — Onboarding wizard provider integration.** Once EP-22 lands, wire the onboarding wizard's Step 3 (§11) to the real Connect-Provider flow instead of routing to `/connections`. The wizard itself no longer needs to be built — only re-pointed. Not started.
6. **EP-25 — Transactional email.** One implementation; fixes verification, password reset, and member invites at once. Not started.
7. **EP-26 — Website content completion.** Real copy for the 9 existing stub pages, plus net-new pages the product spec calls for that don't exist in the source repo at all: **Enterprise, Integrations, Roadmap, Careers, Status**. Not started.
8. **EP-27 — Billing.** Still fully absent (no Stripe/subscription code anywhere per the prior audit) — correctly last, since there's no self-serve product to charge for until EP-21–24 land. Not started.

Full rationale, the component/token reconciliation tables, and the "what this plan deliberately does not recommend" section live in `docs/costorah_website_dashboard_merge_plan.md`.

## 9. EP-21 — Honest Status Against the Stated Success Criteria

The success criteria for this initiative were: `costorah.com` fully functional, `app.costorah.com` fully functional, one shared design system, one shared authentication system, both documented in `CLAUDE.md`, no duplicate components, all tests pass.

**What is actually true right now:**
- Both apps build, lint, and test green, independently, from a verified fresh clone, in one pnpm workspace. Re-verifiable at any time (`pnpm --filter @costorah/dashboard build/test`, `pnpm --filter @costorah/website build/test`).
- **One shared authentication system, now actually unified, not just "not duplicated yet."** A single `User`/`Organization`/`Membership`/`Session` table set backs both apps. `apps/website`'s `/signup`/`/login` call the real backend and set an httpOnly session cookie; `apps/dashboard` receives that same session via a one-time URL-fragment handoff into its existing bearer-token store (§6) — there is no second account store, no "personal login" vs. "organization login," exactly as EP-21.2 required. The one open item is cosmetic: the dashboard's own client still carries tokens via Zustand rather than the cookie directly, which is a compatible implementation detail, not a second auth system.
- **A completely new user can complete the full acceptance-criteria flow without operator intervention**: `costorah.com/signup` → `POST /v1/auth/register` creates the `User` + personal `Organization` (`is_personal=True`) + `OWNER` `Membership` in one transaction → session cookie set → redirect to `app.costorah.com/onboarding` with the session handed off → dashboard is authenticated, workspace already selected → 5-step onboarding wizard → `/dashboard`. Verified in pieces (backend curl round-trip including cookie-only `/me`, website SSR render, dashboard handoff unit tests, dashboard build/lint/typecheck/test) — not yet re-verified as one continuous browser session end-to-end.
- "No duplicate components remain" is **still not true**. One concrete duplication (`cn()`) is eliminated. The much larger one — `apps/website`'s 38 unused shadcn/ui primitives vs. `apps/dashboard`'s ~14 hand-rolled equivalents (`Dialog`, `Popover`, `Avatar`, `ConfirmDialog`, `ToastContainer`, etc.) — has not been touched. That's milestone 5, unstarted. `apps/dashboard` also still has its own `Login.tsx` etc. running alongside the website's now-real `/login` — intentionally kept (§6) until the dashboard adopts `credentials: "include"`.
- `app.costorah.com` / `costorah.com` as live, deployed domains: not part of this repo's scope to stand up (DNS/hosting/Cloudflare account access), and not attempted — the architecture (§0) and each app's independent build are what this repo controls.

This section exists so a future reader (or a future EP) doesn't have to reverse-engineer "how much of EP-21 is actually done" from commit messages — update it every time a milestone in §8 changes state.

---

## 10. Website Production Deployment Audit (Cloudflare)

Triggered by three reported production symptoms: (1) nav links to `/features`, `/pricing`, `/security`, `/developers`, `/docs`, `/blog`, `/about` 404 on the live site; (2) `/signup` and `/login` fail with "Could not reach the server."; (3) suspected CORS gap. Audited by directly exercising the built artifacts (dev SSR, and the actual Nitro worker bundle under `wrangler dev`), not by inspecting the live site — this session has no access to the Cloudflare account, and the agent proxy explicitly denies (403, policy) outbound requests to the production Render host, so the live backend's real CORS headers could not be captured directly either. Findings below are grounded in what the repo's own build output does, cross-checked against Nitro/Cloudflare's documented behavior.

### Files changed
- `backend/app/config/settings.py` — added `"https://www.costorah.com"` to `api_cors_origins`.

That is the only source change this audit required. Every other finding below is a **deployment-configuration** issue, not a code defect — see each root cause for why no other file needed to change.

### Root cause 1 — Nav 404s: not a code bug

Every one of TanStack Router's checks came back clean:
- All 13 route files exist under `apps/website/src/routes/` (`features.tsx`, `pricing.tsx`, `security.tsx`, `developers.tsx`, `docs.tsx`, `blog.tsx`, `about.tsx`, plus `privacy`, `terms`, `contact`, `login`, `signup`, `index`), each a correctly-formed `createFileRoute("/path")(...)`.
- The committed, generated `src/routeTree.gen.ts` registers all 13 routes and matches `src/routes/` exactly — not stale.
- `SiteNav.tsx`'s `links` array `to` values match every route path exactly (`/features`, `/pricing`, `/security`, `/developers`, `/docs`, `/blog`, `/about`).
- No lazy-loading, import, or `tsconfig` issue — `apps/website/tsconfig.json` resolves cleanly (verified via `pnpm typecheck`, clean).

Direct verification, not just static inspection: `npx vite dev` (SSR dev mode) returned `200` for all 13 routes; separately, `pnpm build` then `npx wrangler dev` against the **actual built Cloudflare Worker artifact** (`.output/server/`) also returned `200` for all 13 routes and a correct `404` for a genuinely nonexistent path. The application code is not the source of the reported 404s.

The build's own `nitro.json` records `"preset": "cloudflare-module"` — Nitro builds this app as a **Cloudflare Worker with static assets** (deployed via `wrangler deploy` / Cloudflare's git-connected "Workers Builds"), producing `.output/server/index.mjs` + a generated `wrangler.json` (`main: "index.mjs"`, `assets.directory: "../public"`). It does **not** produce a `_worker.js` file, which is the specific artifact a **Cloudflare Pages** project (Pages "Advanced Mode") looks for to run server-side code. If the live site is set up as a Cloudflare **Pages** project with its build output directory pointed at `apps/website/.output/public`, Cloudflare finds no `_worker.js` there (only `_headers`, `assets/`, `favicon.ico` — no HTML at all, since nothing is prerendered), falls back to pure static-asset serving, and returns Cloudflare's own 404 for every route that isn't a literal file — which matches the reported symptom exactly. This is a **deployment-target mismatch** (Pages vs. Workers), not an application bug. See the deployment checklist below for the exact fix.

### Root cause 2 — Registration "Could not reach the server."

Audited `apps/website/src/lib/api.ts`:
- **URL called**: `${BASE_URL}/v1/auth/register` (and `/v1/auth/login`), `POST`, `credentials: "include"`.
- **`BASE_URL` source**: `import.meta.env["VITE_API_BASE_URL"] ?? "http://localhost:8000"` — a Vite-inlined env var, not hardcoded.
- **Expected env var**: `VITE_API_BASE_URL` (and `VITE_DASHBOARD_URL` for the post-auth redirect).

Verified across environments:
- **Local development**: `.env.development` (committed) sets `VITE_API_BASE_URL=http://localhost:8000` — correct, matches the local backend.
- **Production source-of-truth**: `.env.production` (committed) already sets `VITE_API_BASE_URL=https://ai-finops-bqf3.onrender.com` and `VITE_DASHBOARD_URL=https://app.costorah.com`. `pnpm build` (Vite's default mode is `production`, which loads this file) was run and the **actual compiled output** — both the SSR server bundle (`.output/server/_ssr/authSchemas-*.mjs`) and the client browser bundle (`.output/public/assets/authSchemas-*.js`) — was inspected directly: both have `https://ai-finops-bqf3.onrender.com` baked in as the resolved value, not `localhost`. The `?? "http://localhost:8000"` fallback is present in the bundle as dead code (Vite/esbuild inline the whole `import.meta.env` object; the fallback is unreachable once the key is defined) but is never actually selected.
- **Cloudflare deployment**: cannot be inspected directly (no dashboard access from this session). Per `.env.production`'s own header comment, a `VITE_API_BASE_URL` set in Cloudflare's project environment variables would override the committed file at build time — if that variable is unset, blank, or was never migrated from an earlier Lovable-hosted config, the build would silently fall back to whatever is committed (currently correct) or, in a misconfigured project, to something stale. This could not be confirmed or ruled out from this session; see the Cloudflare variables table below.

Given the committed config resolves correctly and was proven correct in the actual compiled artifact, the more likely explanation for a **live** "Could not reach the server." failure — assuming Cloudflare's env vars aren't overriding this — is CORS: a browser `fetch()` blocked by CORS throws a generic, non-`ApiError` exception, which `signup.tsx`/`login.tsx`'s catch-all branch renders as exactly this message (see `apps/website/src/routes/signup.tsx`'s final `else` branch). That points directly at root cause 3.

### Root cause 3 — CORS gap (fixed)

`backend/app/main.py` wires `CORSMiddleware` from `settings.api_cors_origins` with `allow_credentials=True` (required, since the website's fetches use `credentials: "include"`). Before this audit, `app/config/settings.py`'s `api_cors_origins` allow-listed `https://costorah.com` and `https://app.costorah.com` but **not `https://www.costorah.com`**. Any traffic actually served from the `www` subdomain (a common apex/`www` split) would have every `/v1/auth/register`/`login` request blocked by the browser's CORS check before it ever reaches the backend — surfacing in the UI as "Could not reach the server.", indistinguishable from a real outage.

**Fix applied**: added `"https://www.costorah.com"` to `api_cors_origins`. `https://costorah.com` and `https://app.costorah.com` were already present and required no change. (A pre-existing, unrelated `https://op.0protocol.net` entry is also in this list — it's this repo's demo/seed-data domain from `app/db/seed.py`'s `admin@0protocol.net` fixture user, unrelated to Costorah's own domains; left untouched as out of scope for this audit.)

### Cloudflare environment variables (apps/website build)

| Variable | Purpose | Example value |
|---|---|---|
| `VITE_API_BASE_URL` | Backend API origin the website's `fetch()` calls target (`src/lib/api.ts`). Baked into the build at compile time — not read at runtime. | `https://ai-finops-bqf3.onrender.com` |
| `VITE_DASHBOARD_URL` | Origin the browser is redirected to after a successful register/login, carrying the session handoff fragment (`buildDashboardHandoffUrl()`, §6). | `https://app.costorah.com` |

No other `import.meta.env.VITE_*` variables exist in `apps/website/src` (verified by exhaustive grep). Both variables already have correct committed defaults in `.env.production`; Cloudflare project variables only need to be set explicitly if they must differ from those committed defaults, or to make the production values visible/auditable in the Cloudflare dashboard independent of the repo.

### End-to-end trace: `costorah.com` → Register → Backend → User → Personal Workspace → Redirect → Dashboard

| Step | Status | Notes |
|---|---|---|
| `costorah.com` loads, nav renders | Code verified working (dev SSR + built Worker artifact, all 13 routes 200) | Live-site 404s traced to deployment target (Pages vs. Workers), not code — see root cause 1 |
| User clicks Register, submits form | Code verified working | `signup.tsx` client validation (zod) confirmed via existing tests |
| Browser calls `POST https://ai-finops-bqf3.onrender.com/v1/auth/register` | **Blocked by CORS if origin is `www.costorah.com`** (fixed this audit) or if Cloudflare's `VITE_API_BASE_URL` diverges from the correct committed value (unverifiable from this session) | Both failure modes render identically as "Could not reach the server." |
| Backend creates `User` + personal `Organization` (`is_personal=True`) + `OWNER` `Membership`, issues session cookie | Verified correct in EP-21.2 (§6, §7) via direct curl round-trip against a local backend | Not re-verified against the live Render deployment (no access) |
| Redirect to `app.costorah.com/onboarding#session=...` | Code verified working (`buildDashboardHandoffUrl`, dashboard `consumeSessionHandoff.ts`, both covered by tests) | Requires `VITE_DASHBOARD_URL` to be correctly set at build time (see table above) |
| Dashboard consumes the handoff, lands on `/onboarding`, completes wizard, reaches `/dashboard` | Verified via dashboard unit tests and build | Not re-verified as one continuous live browser session (same caveat as §9) |

**Every failure point identified in this trace is a deployment-configuration issue** (Cloudflare project type/build settings, and — now fixed — a missing CORS origin), not an application code defect. No route, component, or API-client code needed repair.

### Deployment checklist

1. **Cloudflare project type**: confirm the site is deployed as a **Cloudflare Worker (with static assets)** — via `wrangler deploy` or Cloudflare's git-connected "Workers Builds" — not as a "Cloudflare Pages" project in static/Advanced-Mode. Nitro's `cloudflare-module` preset (this repo's build output) targets Workers, not Pages' `_worker.js` convention.
2. **Build command**: `pnpm install --frozen-lockfile && pnpm --filter @costorah/website... build` (the `...` selector is required — see §2's Monorepo Build Rule — so `packages/shared-ui` builds before `apps/website`).
3. **Deploy artifact**: `apps/website/.output/server/` (contains `index.mjs` + generated `wrangler.json`); deploy with `npx wrangler deploy` from that directory, or point Workers Builds at it.
4. **Environment variables** (Cloudflare project settings): set `VITE_API_BASE_URL` and `VITE_DASHBOARD_URL` per the table above, or confirm the committed `.env.production` defaults are correct and intentionally left unoverridden.
5. **Backend CORS** (Render): confirm `api_cors_origins` (now including `https://www.costorah.com`) is deployed — this is a code change, ships automatically on the backend's next deploy from `main`.
6. **Backend session cookie domain** (Render): confirm `SESSION_COOKIE_DOMAIN=.costorah.com` is set in Render's environment (§6) — without it, the cookie defaults to host-only and won't be valid across `costorah.com` → `app.costorah.com`.
7. **Post-deploy smoke test**: load `https://costorah.com/features` (and the other 6 previously-404ing routes) directly — confirms the Worker (not static-only) is serving; submit `/signup` — confirms CORS + `VITE_API_BASE_URL` are both correct end-to-end.

This audit could not directly confirm items 1 and 4 against the live Cloudflare project (no dashboard access from this session) — they're the two items most likely still open. Re-run the smoke test in item 7 after applying them.

---

## 11. EP-21.3 — First-Time User Onboarding

**Status: complete.** Replaces the EP-21.2-era `/onboarding` wizard's step content with the product-spec'd 5-step flow, adds real server-side persistence for completion (so it only ever shows once, on any device), and a workspace-rename endpoint.

### Flow

```
POST /v1/auth/register or /login  (website or dashboard)
        │
        ▼
ProtectedRoute (apps/dashboard) checks user.onboarding_completed
        │
        ├── false ──► /onboarding
        │                │
        │                ▼
        │        Step 1 Welcome  →  Step 2 Workspace  →  Step 3 Provider  →  Step 4 Tour  →  Step 5 Finish
        │                                                                                          │
        │                                              POST /v1/auth/onboarding/complete ◄─────────┘
        │                                                       │
        │                                                       ▼
        │                                            users.onboarding_completed_at = now()
        │                                                       │
        └── true ──────────────────────────────────────────────┴──► /dashboard (or wherever was requested)
```

`ProtectedRoute` (`apps/dashboard/src/components/ProtectedRoute.tsx`) is the single enforcement point — it redirects to `/onboarding` whenever `user.onboarding_completed === false`, regardless of entry path (website registration handoff, website login handoff via §6's fragment mechanism, or the dashboard's own `/login`), and does nothing when the value is `true` or `undefined` (unknown — see "Known limitations" below). This replaces having to remember to redirect at every login/register call site with one rule that cannot be forgotten at a new entry point.

### Steps (`apps/dashboard/src/features/Onboarding.tsx`)

1. **Welcome** — greets the user by first name, explains the product in five bullets (monitor costs, optimize tokens, control spend, alerts, analytics). No backend call.
2. **Workspace** — shows the current `Organization`'s name (editable, saved via the new `PATCH /v1/organizations/{org_id}`) and slug (read-only, by design — slugs are assigned once at registration and never change as a side effect of a rename). Fetches via the existing `GET /v1/organizations`.
3. **Choose Provider** — displays cards for the 7 providers named in the product spec (OpenAI, Anthropic, Google Gemini, OpenRouter, Azure OpenAI, Grok, Ollama), sourced from the existing `PROVIDER_CATALOG` (`src/lib/providerCatalog.ts`) rather than a new hardcoded list. **No provider CRUD is built here** — `ProviderConnection` has no persistence API yet (EP-22, not started). "Connect provider" routes to the existing `/connections` page (live connectivity checks against server-side credentials — the closest real, working feature today); "Skip for now" advances to the next step. Both paths are honest about the gap rather than faking a connect flow.
4. **Product Tour** — a static grid explaining Dashboard, Projects, API Keys, Budgets, Alerts, Usage, Analytics. No video, no backend call.
5. **Finish** — "Go to dashboard" and "Connect provider" both call `POST /v1/auth/onboarding/complete` before navigating (so leaving the wizard via either button counts as done), then navigate to `/dashboard` or `/connections` respectively.

Every step reuses `apps/dashboard`'s existing design system (`glass-card`, `btn-primary`/`btn-ghost`, Framer Motion transitions, `IconBadge`/`StepShell` patterns carried over from the EP-21.2 version) — no new component primitives were introduced.

The pre-existing `OnboardingModal.tsx` (a separate, shorter "welcome + theme picker + tour" popup shown once inside `AppLayout`, gated by its own `localStorage`-only `useOnboardingStore` flag) is untouched, but the wizard's Finish step calls `useOnboardingStore`'s `complete()` too, so it never pops up redundantly right after a user finishes the real onboarding flow.

### Backend changes

- **`users.onboarding_completed_at`** (migration `a3c8e21f5b7d`, chained off `fe2f617c934d`) — nullable timestamp, `NULL` = not completed. No new table; follows the same single-nullable-column pattern EP-21.2 used for `organizations.is_personal`. **Backfilled** in the same migration (`UPDATE users SET onboarding_completed_at = now() WHERE ... IS NULL`) so every pre-existing user is treated as already onboarded — the correct default is the *opposite* of a fresh boolean-with-`false`-default column here, since retroactively showing onboarding to people who already know the product would be a regression, not a fix. Only users created after this migration runs start `NULL`.
- **`AuthService.complete_onboarding(user)`** (`app/auth/service.py`) — mutates `user.onboarding_completed_at` directly and flushes, matching the existing `verify_email`/`reset_password` mutation pattern (not a new repository bulk-update method, since the endpoint already has a session-bound `User` instance via `CurrentUser`).
- **`POST /v1/auth/onboarding/complete`** — new endpoint, `CurrentUser`-authenticated, idempotent, returns `UserPublic`.
- **`UserPublic.onboarding_completed: bool`** — added to the shared response schema, so it's present on `POST /register`, `POST /login`, `GET /me`, and the new complete-onboarding endpoint's response with zero extra plumbing.
- **`PATCH /v1/organizations/{org_id}`** — new endpoint (`app/api/v1/organizations.py`), `ORG_WRITE` permission (OWNER/ADMIN only, reused — no RBAC changes), renames `name` only via the existing generic `OrganizationRepository.update()`.

### Frontend changes

- `apps/dashboard/src/stores/auth.ts` — `AuthUser.onboarding_completed?: boolean` (optional: a session persisted before this field existed won't have it — see "Known limitations").
- `apps/dashboard/src/types/backend.ts` — `BackendUserPublic.onboarding_completed: boolean` (required — the backend always sends it now).
- `apps/dashboard/src/services/api.ts` — `getMe()`, `completeOnboarding()`, `updateOrganization(id, name)`.
- `apps/dashboard/src/components/ProtectedRoute.tsx` — the onboarding-gate redirect (above), plus a best-effort `GET /v1/auth/me` call folded into the existing silent-token-refresh path, so a persisted session that predates `onboarding_completed` self-heals the next time its access token needs refreshing (which is every page reload, since the access token is memory-only) rather than staying stale until the next full login.
- `apps/dashboard/src/lib/consumeSessionHandoff.ts` — carries `onboarding_completed` through the website→dashboard fragment handoff (§6).
- `apps/website/src/lib/api.ts` — `UserPublic.onboarding_completed: boolean` added so the field survives the handoff payload construction unchanged.

### Testing

- **Backend** (`backend/tests/test_ep21_3_onboarding.py`, 11 new tests): `AuthService.complete_onboarding` (sets timestamp, idempotent); `POST /v1/auth/onboarding/complete` (200 + `onboarding_completed: true`, 401 unauthenticated); `onboarding_completed` surfaced correctly on `/me` and `/register`; `PATCH /v1/organizations/{org_id}` (owner can rename, member gets 403, empty name is 422, unauthenticated is 401). Full backend suite: **1478 passed** (1467 + 11), ruff/mypy/black clean.
- **Frontend** (`apps/dashboard`, 6 new tests): `ProtectedRoute.test.tsx` (5 tests — redirects incomplete users to `/onboarding` from any protected route, does not loop when already there, does not force a redirect for `undefined`/unknown status, still redirects unauthenticated users to `/login`); `consumeSessionHandoff.test.ts` extended with 1 test verifying `onboarding_completed` survives the handoff. Full dashboard suite: **136 passed** (130 + 6), lint clean, typecheck clean, build clean.
- **Website**: unaffected by this EP's `UserPublic` type addition — full suite (14 tests) and build re-verified green.

### Known limitations

- A dashboard session persisted before this EP shipped will have `AuthUser.onboarding_completed === undefined` until its access token is next refreshed (self-heals automatically, per the `ProtectedRoute` change above — in practice this is at most one page reload for most sessions, since the access token is memory-only). `undefined` is treated as "don't force onboarding," not as "not completed," to avoid surfacing the wizard to users who never should have seen it.
- Step 3 (Choose Provider) still cannot fully "connect" a provider with a customer-supplied credential — that requires a secrets vault, which doesn't exist yet (see §12's ProviderConnection scope note). ProviderConnection CRUD itself is now real (§12), and the wizard's "Connect provider" button correctly routes to the `/connections` page where a connection record can actually be created — this is disclosed in the step's own copy, not hidden.
- No automated end-to-end browser test of the full register → onboarding → dashboard journey exists yet (same caveat as §9/§10 — verified in pieces: backend endpoint tests, frontend component/redirect tests, builds — not as one continuous live browser session).

### Next milestone recommendation

A separate, much larger message arrived mid-EP asking to redefine "EP-21.3" as "Frontend Completion & Dashboard Integration," including full Provider CRUD and Projects CRUD — which conflicted with this repo's own roadmap at the time (§8 had those scoped as not-yet-started EP-22/EP-23, since the backend had no persistence API for either). That request was paused rather than guessed at, and resolved properly as its own initiative — see §12, which delivers exactly the backend work (EP-22, EP-23) that request actually needed, plus real frontend management UI on top of it. §12's "Next milestone" carries forward from here.

---

## 12. EP-22 + EP-23 — Provider Connections & Projects CRUD (Dashboard Integration)

**Status: Priorities 1–2 of the "Frontend Completion & Dashboard Integration" request complete (real backend + real frontend, tested). Priorities 3–9 audited; findings and honest scope below — not a full pass, see "Known limitations."**

### Why this became EP-22 + EP-23, not a UI-only pass

The request's Priority 1 ("Add provider / Edit provider / Delete provider") and Priority 2 ("Create/Rename/Delete Project") both require persisted CRUD for entities that had models and repositories (`Project`, `ProviderConnection` — both already existed, from earlier EPs) but **no API router at all**. "Backend changes should only be made if absolutely required" — for these two, it was: there was no existing endpoint to reuse, and building the requested UI without one would mean either fabricating fake success responses or leaving the buttons non-functional. Both are exactly what this project's standing no-fake-functionality rule (§9, §10) forbids. So the backend work below is that "absolutely required" case — not scope creep, and it was reused everywhere reuse was possible (permissions, repositories, the generic `BaseRepository.update()`/`soft_delete()`, the existing `RequirePermission` dependency — no RBAC changes, no new tables, no migration).

### Backend — Projects CRUD (EP-22 roadmap item's sibling, EP-23)

- `app/schemas/projects.py` (new) — `ProjectResponse`, `ProjectsListResponse`, `CreateProjectRequest`, `UpdateProjectRequest`.
- `app/api/v1/projects.py` (new) — `GET/POST /v1/organizations/{org_id}/projects`, `PATCH/DELETE /v1/organizations/{org_id}/projects/{project_id}`. `PROJECT_READ`/`PROJECT_WRITE`/`PROJECT_DELETE` (all pre-existing permissions, already granted per-role since EP-13 — VIEWER+ can read, MEMBER+ can write, **ADMIN+ only** can delete). Built entirely on the pre-existing `Project` model and `ProjectRepository` — no migration.
- Registered in `app/api/router.py`.

### Backend — Provider Connections CRUD (EP-22)

- `app/schemas/provider_connections.py` (new) — `ProviderConnectionResponse`, list/create/update request schemas, `TestProviderConnectionResponse`.
- `app/api/v1/provider_connections.py` (new) — `GET/POST /v1/organizations/{org_id}/provider-connections`, `PATCH/DELETE .../{connection_id}`, `POST .../{connection_id}/test`. `PROVIDER_READ` (every role) / `PROVIDER_WRITE` / `PROVIDER_DELETE` (**ADMIN+OWNER only** — MEMBER has read but not write/delete, per the pre-existing `app.auth.rbac` permission grants). Built on the pre-existing `ProviderConnection` model and `ProviderConnectionRepository` — no migration.
- **Deliberately not built: per-connection API key/secret storage.** `ProviderConnection`'s own docstring says credentials belong in a "Secrets store, by reference" — no such store exists anywhere in this codebase. Storing a raw customer API key in a new ad-hoc column would be a real security regression, not a shortcut. So a `ProviderConnection` here is metadata only (type, display name, active/inactive, project scoping, health) — genuinely useful (the health/test/activate-deactivate lifecycle is fully real), but not yet "paste your OpenAI key and go." A secrets vault is the next real blocker for that, tracked below.
- **"Test connection" reuses the existing connectivity probe** (`app/api/v1/providers.py`'s `_require_supported`/`_get_adapter`, which authenticates via server-side environment-variable credentials) rather than building a second, parallel testing path. Only `openai`/`anthropic` have production-ready adapters today (`_PRODUCTION_PROVIDERS`); testing any other provider type returns `tested: false` with an honest "no adapter yet" message instead of a fake result — this is why the endpoint doesn't error on the other 5 providers named in the product spec (Google Gemini, OpenRouter, Azure OpenAI, Grok, Ollama), it just tells the truth about what it can verify today.
- Registered in `app/api/router.py`.

### Frontend

- `apps/dashboard/src/services/api.ts` — `listProjectsCrud`/`createProject`/`updateProject`/`deleteProject`, `listProviderConnections`/`createProviderConnection`/`updateProviderConnection`/`deleteProviderConnection`/`testProviderConnectionById`.
- **Projects** (`apps/dashboard/src/features/Projects.tsx`) — added a "Manage projects" section (create via inline form, inline rename, delete via the existing `ConfirmDialog`) above the page's pre-existing spend-analytics cards. Deliberately additive, not a replacement: the existing cards are a *usage-derived analytics view* (`GET /v1/dashboard/projects`, only shows projects with spend data in the selected period) while the new section is a *management view* of the `Project` entity itself (shows every project, including ones with zero usage) — different data sources serving different, complementary purposes on the same page.
- **Provider Connections** (`apps/dashboard/src/features/Connections.tsx`) — added a "Your provider connections" section (add via inline form with a provider-type dropdown covering exactly the 7 providers the product spec names, rename, activate/deactivate, test, delete) above the page's pre-existing per-provider connectivity-probe cards. Same reasoning: the existing cards test *server-side* credentials for the 2 production adapters; the new section manages *persisted connection records* for all 7 named providers. `apps/dashboard/src/features/Providers.tsx` (the cost/usage-breakdown-by-provider analytics page) was intentionally left untouched — it's an analytics page, not a connections page, and `/connections` was the better-fitting, already-existing home for this per "reuse, don't recreate."
- Both sections use `EmptyState` (not a blank page) when the org has none yet, and route their own errors through `toast.error`/`toast.success` — no new toast/empty-state primitives introduced.

### Priorities 3–9 — audit findings (not all re-implemented this pass)

- **Priority 3 (Workspace Settings)**: audited. `apps/dashboard/src/features/Settings.tsx` still does not call `updateOrganization` (added in EP-21.3) or persist anything else to the backend — this is the same pre-existing gap CLAUDE.md has documented since the EP-21 migration ("`Settings.tsx` doesn't persist anything to the backend despite a full save UI"), confirmed still true, not newly introduced. Not fixed in this pass — it's a substantial page (843 lines, 6 tabs) that deserves its own focused pass rather than a rushed edit alongside two new CRUD systems.
- **Priority 4 (Dashboard live data)**: audited, not re-verified line-by-line. Per §8/EP-19.2, the dashboard's KPIs, activity feed, and notification center were already wired to real endpoints in a prior EP; this pass did not find or introduce any new placeholder cards.
- **Priority 5 (Navigation audit)**: done. Every entry in `apps/dashboard/src/lib/navigation.ts` (`NAV_ITEMS`, the single source shared by the sidebar and command palette) was checked against `App.tsx`'s registered routes — all 14 resolve to a real route and render. `/audit-logs` is the one intentional exception, and it's an honest `Placeholder` (documented endpoint it's waiting on), not a dead link.
- **Priority 6 (Empty states)**: done for the two sections built this EP (see above). Not audited across every other existing page.
- **Priority 7 (UI polish)**: the two new sections reuse the existing design system (`Section`, `EmptyState`, `ConfirmDialog`, `btn-primary`/`btn-ghost`/`btn-outline`, `badge`, toast) with no new primitives — consistent by construction, not by a separate polish pass. No dedicated responsive/loading/error audit was run across the rest of the app.
- **Priority 8 (Authentication)**: not re-audited this pass — covered in depth by EP-21.2/EP-21.3 (§6, §11), unchanged here.
- **Priority 9 (API integration audit)**: partial. This pass's own two new endpoint groups are fully wired (nothing left "built but unused"). A repo-wide "every backend endpoint: used / partially used / unused" inventory was not produced — that's a larger, standalone audit task.

### Testing

- **Backend**: 22 new tests — `backend/tests/test_ep23_projects.py` (10: list/create/update/delete, role-permission checks for VIEWER/MEMBER/ADMIN, validation) and `backend/tests/test_ep22_provider_connections.py` (12: list/create/update/delete/test, including the "unsupported provider returns untested rather than erroring" case, and the ADMIN-vs-MEMBER permission boundary). Full backend suite: **1500 passed** (1478 + 22), ruff/black/mypy clean.
- **Frontend**: 10 new tests — `apps/dashboard/src/__tests__/ManageProjectsSection.test.tsx` and `ManageConnectionsSection.test.tsx` (empty state, list rendering, create, rename, delete-with-confirm, test-connection), following the same `vi.mock("../services/api")` + `QueryClientProvider` pattern as the existing `ApiKeys.test.tsx`. Full dashboard suite: **146 passed** (136 + 10), lint clean, typecheck clean, build clean (both `tsc --noEmit` and the stricter `tsc -b` project-build path the actual `build` script uses).

### API endpoints added

| Method | Path | Permission |
|---|---|---|
| GET | `/v1/organizations/{org_id}/projects` | `PROJECT_READ` |
| POST | `/v1/organizations/{org_id}/projects` | `PROJECT_WRITE` |
| PATCH | `/v1/organizations/{org_id}/projects/{project_id}` | `PROJECT_WRITE` |
| DELETE | `/v1/organizations/{org_id}/projects/{project_id}` | `PROJECT_DELETE` |
| GET | `/v1/organizations/{org_id}/provider-connections` | `PROVIDER_READ` |
| POST | `/v1/organizations/{org_id}/provider-connections` | `PROVIDER_WRITE` |
| PATCH | `/v1/organizations/{org_id}/provider-connections/{connection_id}` | `PROVIDER_WRITE` |
| DELETE | `/v1/organizations/{org_id}/provider-connections/{connection_id}` | `PROVIDER_DELETE` |
| POST | `/v1/organizations/{org_id}/provider-connections/{connection_id}/test` | `PROVIDER_WRITE` |

### Known limitations

- No secrets vault — `ProviderConnection` cannot yet hold a customer-supplied API key. This is the concrete next blocker for a real "paste your key and go" connect flow (see §7's original note on this, still accurate).
- Settings page (Priority 3) still not wired — see above.
- The Projects page now has two different "projects" data sources on one screen (analytics cards vs. management list) which, while each internally consistent, could read as confusing without the section headers distinguishing them; a future pass could consider merging them once the analytics endpoint also returns zero-usage projects.
- Priorities 4, 8, 9 were not re-verified from scratch this pass (see above) — asserting they're "done" would overstate what was actually checked in this EP.

### Next milestone recommendation

**A secrets vault** (or at minimum, an encrypted-column credential store scoped to `ProviderConnection`) is the single blocker shared by the two biggest remaining gaps: real "Connect Provider" (onboarding Step 3, §11, and this section's Connections UI) and Priority 3's Workspace/API-key-adjacent settings. After that, a focused Settings.tsx pass (Priority 3) is the next highest-value, well-scoped piece of the original request.

**Update, EP-22 (below): the secrets-vault gap named above is now closed** — `ProviderConnection` holds a real, encrypted, per-connection API key, validated live against all 7 named providers. The Settings.tsx wiring gap (Priority 3) remains open and is EP-22's own recommended next milestone — see §13's own "Next milestone recommendation."

---

## 13. EP-22 — Secure Provider Credentials & Connection Validation

**Status: complete.** Converts `ProviderConnection` from metadata-only (§12) into a fully functional, production-ready integration: encrypted per-connection API keys, live validation against all 7 named providers on save/rotate/test, normalized health/error reporting, and a real credential-management UI. This closes the "no secrets vault" gap §12 flagged as its own next blocker.

### Why this needed real backend work, not just a UI pass

§12 deliberately did not store credentials because no encryption abstraction existed and 5 of the 7 named providers (Grok, Google, Azure OpenAI, OpenRouter, Ollama) had stub adapters whose `verify_auth()` raised `NotImplementedError` — only OpenAI and Anthropic had production-ready live validation (`app/api/v1/providers.py`'s `_PRODUCTION_PROVIDERS`). Building real credential storage without also finishing those 5 adapters would mean either faking validation results or shipping a "save" button that couldn't tell a user whether their key actually works. Both are exactly what this project's no-fake-functionality convention (§9, §10, §12) forbids. So EP-22 is genuinely two things bundled: (1) encryption + credential CRUD, and (2) finishing the provider adapter framework EP-06/EP-07 left at 2-of-7 complete — reusing that same framework throughout rather than building a second one.

### Architecture

```
Frontend (apps/dashboard/src/features/Connections.tsx)
        │  POST/PATCH/rotate — plaintext key travels over HTTPS only, once
        ▼
API layer (app/api/v1/provider_connections.py)
        │
        ├─► ProviderCredentialService  (app/services/provider_credential_service.py)
        │       encrypt() / decrypt() / masked() — the ONLY call site permitted
        │       to decrypt a stored key. Depends on EncryptionService's
        │       encrypt()/decrypt() interface only (dependency inversion).
        │
        ├─► ProviderHealthService  (app/services/provider_health_service.py)
        │       runs a validation probe, persists health_status /
        │       last_validation_status / last_error / last_failure_at /
        │       last_recovery_at / consecutive_failure_count. Backs
        │       create (validate-on-save), POST .../test, and
        │       POST .../rotate — one code path, three entry points, so the
        │       health fields can never drift between them.
        │
        └─► ProviderValidator  (app/providers/validation.py)
                builds the right ProviderConfig subclass (reusing
                app.providers.config from EP-06/EP-07), gets an adapter via
                the existing ProviderFactory + ProviderRegistry, calls
                adapter.verify_auth() with the decrypted key carried as an
                INLINE SecretReference (never persisted, never logged),
                and normalizes the outcome into ProviderValidationStatus.

Storage: app.models.provider_connection.ProviderConnection
        encrypted_api_key  — ciphertext only (EncryptionService.encrypt())
        base_url           — optional override (SSRF-validated by ProviderConfig)
        last_validation_status / last_error — normalized, user-safe
        health_status / last_failure_at / last_recovery_at /
        consecutive_failure_count — unchanged from EP-19.3/§12
```

### Part 1 — Encryption (`app/security/encryption.py`, `app/security/masking.py`)

- **`EncryptionService`** — `encrypt()`/`decrypt()` over `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256, authenticated encryption), keyed by PBKDF2-HMAC-SHA256 (390,000 iterations — OWASP's current minimum) derived from `APP_SECRET_KEY`. No dedicated KMS exists yet, so `APP_SECRET_KEY` is the encryption root, exactly as this EP's own brief allowed ("Use APP_SECRET_KEY ... if no dedicated key-management system exists yet").
- **Dependency inversion**: every caller (`ProviderCredentialService`, and transitively the API router) depends only on `EncryptionService.encrypt()`/`decrypt()`'s signatures — none of them import `Fernet` or know a key derivation happens at all. Swapping to AWS KMS / Azure Key Vault / GCP KMS / HashiCorp Vault later means writing one new class with the same two methods and swapping the `get_encryption_service()` factory (see "Future KMS integration" below) — zero call-site changes.
- **Key rotation**: ciphertext is stored as `"v<version>:<token>"`. A new `APP_SECRET_KEY_PREVIOUS` setting (`app/config/settings.py`) lets `decrypt()` fall back to the pre-rotation key for ciphertext encrypted before a rotation, so rotating `APP_SECRET_KEY` does not require a bulk re-encryption migration — old rows keep decrypting via the previous key until next rotated (`ProviderCredentialService`/rotate endpoint re-encrypts under the current key on next save).
- **Masking** (`mask_secret()`) — display-only transform, e.g. `sk-********************************AbC` (3-char prefix, 4-char suffix, rest starred). Fully masks values too short to safely reveal a prefix+suffix. Never used to protect data at rest — only for what leaves the process in an API response.

### Part 2 — Provider Credentials (model + migration)

`ProviderConnection` (`app/models/provider_connection.py`) gained four columns via migration `c7d4f9a1b3e5` (chained off EP-21.3's `a3c8e21f5b7d`, all nullable additions — no backfill needed, no existing row's behavior changes):

| Column | Purpose |
|---|---|
| `encrypted_api_key` | Ciphertext only. `NULL` = no credential configured (fine for Ollama, or a connection saved before a key was added). |
| `base_url` | Optional per-connection endpoint override. SSRF-validated by `ProviderConfig._check_ssrf` (EP-06/EP-07) at adapter-construction time — the same guard that already protects the env-var-keyed probe endpoints. |
| `last_validation_status` | New `ProviderValidationStatus` enum — see Part 3. |
| `last_error` | Normalized, user-safe error text only — never a raw provider response body, never the credential value. |

The pre-existing `health_status` / `last_failure_at` / `last_recovery_at` / `consecutive_failure_count` (EP-19.3) are unchanged and keep backing the alert engine. `Provider` / `Display Name` / `Organization` / `Project` / `Created` / `Updated` were already present (§12).

### Part 3 — Validation Engine (`app/providers/validation.py`)

`ProviderValidator.validate(provider_type, api_key, base_url)`:
1. Builds the correct `ProviderConfig` subclass (`OpenAIConfig`, `AnthropicConfig`, `GrokConfig`, `GoogleConfig`, `AzureOpenAIConfig`, `OpenRouterConfig`, `OllamaConfig` — all pre-existing from EP-06) with the decrypted key wrapped in a new `SecretStoreType.INLINE` `SecretReference` (`app/providers/config.py`) — the value is the plaintext itself, held only in memory for this one call, never written to logs (the `SecretReference.__repr__` redaction already covers this variant) or persisted.
2. Gets an adapter via the existing `ProviderFactory` + `ProviderRegistry` (EP-06.5) — no new adapter-selection logic.
3. Calls `adapter.verify_auth()` — the real, live probe per provider:

| Provider | Live call | Notes |
|---|---|---|
| OpenAI | `GET /v1/models` | Unchanged from EP-07. |
| Anthropic | `GET /v1/models` | Unchanged from EP-07. |
| Google Gemini | `GET /v1beta/models?key=<key>` | Key travels as a query param (Gemini convention), not a header — new `NullAuth` strategy (`app/http/auth.py`) plus the key passed via request `params`. |
| Azure OpenAI | `GET {azure_endpoint}/openai/deployments?api-version=<v>` | "Deployment validation" per the product spec — Azure has no bare model-list endpoint, only a deployments list, which is the correct live signal. `api-key` header auth. Requires `base_url` (the resource endpoint) — missing one is a config-validation failure, not a network error. |
| OpenRouter | `GET /models` | Named in the product spec. Disclosed limitation: this endpoint is unauthenticated on OpenRouter's side, so it confirms reachability but not key validity — a genuinely bad key is only caught on a later completion call. Documented in the adapter's own docstring, not hidden. |
| Grok (xAI) | `GET /models` | OpenAI-compatible Bearer auth. |
| Ollama | `GET /api/tags` | No credential — "validation" means confirming the local/LAN server is reachable, not verifying a secret (`OllamaConfig.requires_api_key=False`, unchanged from EP-06). |

4. Maps the resulting `app.providers.errors` exception (the existing EP-06/EP-07 hierarchy — `AuthenticationError`, `RateLimitError`, `QuotaExceededError`, `NetworkError`, `InternalProviderError`, `InvalidRequestError`, `ProviderError`) to a `ProviderValidationStatus`:

| Result | `ProviderValidationStatus` | Normalized, user-facing detail |
|---|---|---|
| Success | `healthy` | "Connection healthy." |
| `AuthenticationError` (401, or "forbidden" absent) | `invalid_api_key` | "The API key is invalid or has been revoked." |
| `AuthenticationError` ("forbidden" in message, i.e. 403) | `unauthorized` | "The API key is valid but is not authorized for this operation." |
| `RateLimitError` / `QuotaExceededError` | `quota_exceeded` | "The provider account has exceeded its usage quota or rate limit." |
| `NetworkError` ("timed out" in message) | `timeout` | "The request to the provider timed out." |
| `NetworkError` (other) | `network_failure` | "Could not reach the provider — network error." |
| `InternalProviderError` / other `ProviderError` / `NotImplementedError` | `provider_unavailable` | "The provider is currently unavailable." |

**Every value returned to the frontend (and stored in `last_error`) is one of the seven canned strings above — never `str(exception)`.** This is what "do not expose provider error details directly to users" means in practice: the raw exception (which can carry account IDs, org-scoped billing detail, or other provider-side specifics) never crosses the `ProviderValidator` boundary. `ProviderValidationStatus` is deliberately a finer-grained sibling of the pre-existing `ProviderHealthStatus` (EP-19.3), not a replacement — `health_status` stays the coarse signal the alert engine keys off (`healthy`/`warning`/`critical`/`recovering`/`unknown`); `last_validation_status` is the specific reason behind the most recent transition.

**Extending to an 8th provider** requires exactly one new `match` arm in `ProviderValidator._build_config` plus registering its adapter in `ProviderFactory.build_default_registry` (EP-06) — no other code in the validation, health, or credential layers changes, satisfying this EP's "minimal code changes for future providers" requirement.

### Part 4 — Health Checks (`app/services/provider_health_service.py`)

`ProviderHealthService.check_and_persist(repo, conn, api_key, base_url)` is the single function backing all three "run a validation and save the result" call sites:
- **Save** (`POST /v1/organizations/{org_id}/provider-connections`) — validates immediately whenever there's something to validate (a supplied `api_key`, or a no-credential-required provider like Ollama), so a freshly created connection never sits at a fabricated "unknown" when the answer could be known right away.
- **Test Connection** (`POST .../{id}/test`) — decrypts the stored key (if any) and re-validates on demand.
- **Rotate** (`POST .../{id}/rotate`) — re-validates with the new key immediately after re-encrypting it.

On success: `health_status=HEALTHY`, `last_recovery_at=now`, `consecutive_failure_count=0`. On failure: `health_status` derived from the validation status (see Part 3's table — `invalid_api_key`/`unauthorized`/`provider_unavailable` → `CRITICAL`, `quota_exceeded`/`network_failure`/`timeout` → `WARNING`), `last_failure_at=now`, `consecutive_failure_count += 1`. Frontend health-badge vocabulary (Healthy / Warning / Offline / Invalid Credentials / Unknown) is derived client-side from `last_validation_status` (`VALIDATION_LABELS` in `Connections.tsx`) rather than a 5th backend enum, avoiding a duplicate status vocabulary for the same underlying signal.

### Part 5 — Credential Rotation

`POST /v1/organizations/{org_id}/provider-connections/{connection_id}/rotate` (`RotateProviderConnectionKeyRequest`, `PROVIDER_WRITE`): re-encrypts the supplied key, overwrites `encrypted_api_key`, and re-validates. The previous key is never returned, logged, or diffable from the response — only the ciphertext column changes, and `updated_at` (bumped automatically by `BaseRepository.update()`) plus `last_recovery_at`/`last_failure_at` (set by the post-rotation validation) serve as the audit trail. `UpdateProviderConnectionRequest` (the ordinary metadata-PATCH endpoint) deliberately does **not** accept `api_key` — rotation is a distinct, separately-logged action, not a side effect of renaming a connection (covered by `test_update_does_not_accept_api_key_field`).

### Part 6 — Frontend (`apps/dashboard/src/features/Connections.tsx`)

The EP-22-era "Manage provider connections" section (§12) gained:
- **API key input** — new `ApiKeyInput` component, `type="password"` by default with an `Eye`/`EyeOff` reveal toggle (Part 6's "show masked / reveal toggle" requirement — applies to the *input field while typing*, since the backend never returns a decrypted key to reveal).
- **Base URL field** — optional for most providers, required (and labelled as such) for Azure OpenAI.
- **Masked key display** — `connection.masked_api_key` (e.g. `sk-********************************AbC`) shown inline once a connection has a credential; never the plaintext.
- **Test Connection** — unchanged button, now backed by real per-connection validation instead of §12's env-var-keyed probe.
- **Rotate key** — new inline form (masked `ApiKeyInput` + Save & validate / Cancel), opened via a "Rotate key" button on each row.
- **Health badge / last validation / error message** — `HealthBadge` (unchanged component) plus a new line showing `VALIDATION_LABELS[last_validation_status]` (color-coded success/danger) and `last_error` when present, and "Last checked <timestamp>" derived from `last_recovery_at`/`last_failure_at`.
- **Loading / success / failure states** — `create`/`rotate`/`test` mutations all show a spinner while pending and route through `toast.success`/`toast.warning`/`toast.error` depending on whether the immediate post-save/rotate validation came back healthy — no new toast primitive introduced (reuses the existing `stores/toast.ts`, matching §12's convention).

The pre-existing `ProductionProviderCard`/`IN_DEVELOPMENT_ADAPTERS` section (the *server-side environment-variable* probe from `GET /v1/providers/{provider}/test`, EP-07/PH) is untouched — it's a different, still-accurate mechanism (only OpenAI/Anthropic have that specific env-var-keyed endpoint promoted to "production" status in `app/api/v1/providers.py`'s `_PRODUCTION_PROVIDERS`), unrelated to the per-connection credentials this EP adds.

### Part 7 — Security

- **Never returns decrypted secrets via API** — `ProviderConnectionResponse` has no plaintext field; `masked_api_key` is built by `ProviderCredentialService.masked()`, which decrypts only transiently in-process to compute the mask, then discards the plaintext.
- **Masking format**: `sk-********************************AbC` (3-char prefix, 4-char suffix visible; values too short to safely reveal both are fully masked).
- **Never logs secrets** — the plaintext key exists only as a Python local inside `ProviderCredentialService`/`ProviderValidator`/the adapter's `verify_auth()` call stack; no `structlog` call in any of these paths includes the key, and `SecretReference.__repr__` redacts `lookup_key` even for the new `INLINE` variant that carries a real value.
- **Never includes secrets in exceptions** — every `ProviderError` subclass raised by an adapter carries a fixed, generic message (e.g. `"Invalid API key or unauthorized"` from `map_http_error`, EP-07) that never interpolates the key; `ProviderValidator` additionally re-normalizes even that generic message down to one of the seven canned strings in Part 3's table before it can reach a response or `last_error`.
- **Never exposed in frontend state** — `apps/dashboard` never stores a fetched plaintext key in Zustand/React Query cache; the API key `useState` in `AddConnectionForm`/the rotate form lives only until submit, and the response written back into the connections list cache is the server's masked representation.

### Part 8 — Architecture (service boundaries)

| Service | Responsibility | Depends on |
|---|---|---|
| `EncryptionService` | `encrypt()`/`decrypt()` over Fernet, keyed from `APP_SECRET_KEY` | Nothing provider-specific — pure crypto primitive |
| `ProviderCredentialService` | Encrypt-for-storage / decrypt-for-validation / mask-for-display | `EncryptionService` (interface only) |
| `ProviderValidator` | Live validation probe + error normalization | `ProviderFactory`/`ProviderRegistry`/`ProviderConfig` (EP-06), `app.providers.errors` |
| `ProviderHealthService` | Persist validation outcome onto `ProviderConnection` | `ProviderValidator`, `ProviderConnectionRepository` |

`app/api/v1/provider_connections.py` composes all four; no service imports another's internals, and `ProviderConnectionRepository` (EP-22/EP-23's original repository, §12) is unchanged — it has no idea encryption exists, satisfying "keep provider repositories independent from encryption implementation."

### Future KMS integration

Swapping the encryption root from `APP_SECRET_KEY`-derived Fernet to a cloud KMS is a two-step, call-site-free change:
1. Write a new class (e.g. `KmsEncryptionService`) implementing the same `encrypt(plaintext: str) -> str` / `decrypt(ciphertext: str) -> str` contract as `EncryptionService`, backed by AWS KMS `Encrypt`/`Decrypt`, Azure Key Vault, GCP KMS, or HashiCorp Vault's transit engine.
2. Swap `app.security.encryption.get_encryption_service()`'s body to construct the new class instead.

`ProviderCredentialService`, `ProviderHealthService`, `ProviderValidator`, and the API router all depend on `EncryptionService`'s two-method interface, never its internals — none of them need to change. Existing ciphertext (the `"v1:..."` Fernet tokens) would need either a one-time re-encryption pass under the new KMS, or (simpler) the new service could recognize the `v1:` prefix and delegate decryption of legacy rows to a retained `EncryptionService` instance, mirroring the existing `APP_SECRET_KEY_PREVIOUS` rotation-window pattern.

### Testing

- **Backend**, 3 new files, no live provider keys required (all HTTP mocked via `httpx.MockTransport`, matching the existing `test_ep07.py` pattern):
  - `tests/test_ep22_encryption.py` (16 tests) — round-trip, tamper detection (`InvalidToken` → `EncryptionError`), malformed-ciphertext handling, empty-plaintext rejection, key-rotation fallback (with and without the previous key), masking edge cases, `ProviderCredentialService` never returning plaintext.
  - `tests/test_ep22_provider_validator.py` (18 tests) — full `ProviderValidator` dispatch/normalization matrix (all 7 mapping rows from Part 3's table), config-building edge cases (Azure without `base_url`, an unsupported provider type, Ollama with no key), plus one real-HTTP-shape test per new adapter (Grok, OpenRouter, Google's query-param key, Azure's deployments endpoint, Ollama's tags endpoint and its unreachable-server case) confirming each adapter actually calls the endpoint named in Part 3's table, not just that the dispatch logic is right.
  - `tests/test_ep22_provider_connections.py` (rewritten, 17 tests) — API-level coverage: create-with-key triggers validation, masked key never appears in any response body (asserted via `resp.text` substring checks against the raw plaintext), rotate re-encrypts and re-validates, update endpoint rejects an `api_key` field, RBAC boundaries (ADMIN can create/rotate/delete, MEMBER cannot) unchanged from §12.
  - `tests/test_ep06.py` — 6 tests updated: the 5 stub adapters' `test_verify_auth_not_implemented` tests (now stale, since EP-22 makes `verify_auth()` real) became `test_verify_auth_without_key_raises_authentication_error` / `test_verify_auth_unreachable_raises_network_error` (Ollama), and `test_all_adapters_check_capability_not_implemented` became `test_all_adapters_check_capability_implemented` since every adapter now implements it.
  - Full backend suite: **1509 passed**, ruff/black/mypy clean. Integration tests (`tests/integration/`) still require a live local Postgres/Redis unavailable in this sandbox — same pre-existing, documented limitation as every prior EP's verification (§9, §10).
- **Frontend**, `apps/dashboard/src/__tests__/ManageConnectionsSection.test.tsx` extended with 5 new tests (masked-key display, last-validation-status + error-message display, create-with-key including the reveal-toggle interaction, rotate-key flow) alongside the existing 4 from §12. Full dashboard suite: **150 passed** (146 + 4 EP-22), lint clean, typecheck clean, build clean (both `tsc --noEmit` and the stricter `tsc -b` project-build path — this session again hit and fixed an `exactOptionalPropertyTypes` mismatch in the create-connection request body and an `HTMLElement` vs `HTMLInputElement` test-typing mismatch, both invisible to `tsc --noEmit` alone; see CLAUDE.md §2's "Monorepo Build Rule" section history for why `tsc -b` is the gate that matters).

### Known limitations

- **OpenRouter's validation call does not itself prove the key is valid** (Part 3) — `GET /models` is unauthenticated on OpenRouter's side. A more authoritative check would call OpenRouter's key-introspection endpoint instead; not done here to keep strictly to the "models endpoint" the EP-22 spec named for OpenRouter. Disclosed in the adapter's own docstring, not hidden.
- **No completion/usage calls are exercised by validation** — `verify_auth()` (and therefore `ProviderValidator`) only proves the key can authenticate to a cheap, read-only endpoint; it does not confirm the key has quota or permission for the completion/chat endpoints the SDK would actually use in production. This matches EP-06/EP-07's original scope (`complete()` remains `NotImplementedError` on every adapter) and was not expanded here.
- **`base_url` is accepted per-connection but not exercised by usage ingestion** — EP-16's ingestion path and EP-08's `get_usage()` still use each adapter's default base URL; wiring a customer's `base_url` override into usage collection is out of this EP's scope (validation only).
- **Settings.tsx (Priority 3, §12) is still not wired** — unrelated to this EP, still open from §12's own "known limitations."
- **No secret-scanning / leaked-credential detection** — a customer could paste an already-compromised key and this EP would happily encrypt and validate it; that's a different security control (credential-breach monitoring) out of scope here.

### Next milestone recommendation

With credential storage and live validation now real for all 7 named providers, the highest-value next piece is: (1) **Settings.tsx wiring** (Priority 3, carried forward from §12 — still the largest remaining "full save UI that doesn't persist" gap), and (2) **wiring `ProviderConnection.encrypted_api_key` into actual usage collection** (EP-16's ingestion path and the SDK-facing `get_usage()` calls), so a connected, validated credential doesn't just prove reachability but is the one Costorah actually uses to pull real cost data — closing the loop the product spec's own framing ("Without this, Costorah cannot collect AI usage") points at.

---

## 14. EP-21.3 — First-Time User Onboarding, Post-EP-22 Refresh

**Status: complete.** This is a re-scoping of the original EP-21.3 wizard (§11, shipped before EP-22) to reuse the real, now-persisted Provider Connections CRUD that landed in EP-22 (§13), and to close the "new user lands on a blank dashboard" gap the product spec calls out explicitly. No new backend endpoints, no new tables, no new migration — every persistence and CRUD operation this EP touches already existed.

### Why this is a refresh, not a new EP

§11's wizard was built and shipped correctly for the state of the platform *at the time*: `ProviderConnection` had no credential storage yet, so Step 3 ("Choose your first provider") could only display a static list of provider names and route to `/connections` for the existing env-var-keyed connectivity probe. EP-22 (§13) then built the real thing — encrypted, validated, per-connection credentials — which made §11's Step 3 copy ("Persisted, customer-managed provider connections are coming soon") stale and its functionality strictly worse than what the platform could now actually do. This EP updates Step 3 to use the real thing, and adds the "never land on a blank dashboard" empty-state work the original spec didn't cover. The route (`/onboarding`), the 5-step shape, the backend persistence field (`users.onboarding_completed_at`), and the `ProtectedRoute` enforcement are **all unchanged from §11** — reused exactly as they were, per this EP's own "do not duplicate existing functionality" instruction.

### Flow

```
POST /v1/auth/register or /login  (website or dashboard)  — unchanged, §6/§11
        │
        ▼
ProtectedRoute (apps/dashboard) checks user.onboarding_completed
        │
        ├── false ──► /onboarding
        │                │
        │                ▼
        │        Step 1 Welcome  →  Step 2 Workspace  →  Step 3 Provider  →  Step 4 Tour  →  Step 5 Finish
        │           (unchanged)      (unchanged)          (EP-22 CRUD,        (unchanged)     (unchanged)
        │                                                   this EP)
        │                                                       │
        │                                    AddConnectionForm (features/Connections.tsx,
        │                                    exported & reused verbatim) creates a real,
        │                                    encrypted, validated ProviderConnection —
        │                                    same row the /connections page manages after
        │                                                       │
        │                                              POST /v1/auth/onboarding/complete ◄── Finish
        │                                                       │
        │                                                       ▼
        │                                            users.onboarding_completed_at = now()
        │                                                       │
        └── true ──► /dashboard, or, if a completed user opens /onboarding directly
                      (bookmark, back button), Onboarding.tsx itself redirects to
                      /dashboard immediately — new in this EP, see "Routing" below.
                                                                  │
                                                                  ▼
                                                    Overview.tsx: GettingStartedBanner
                                                    (new, this EP) — prompts to connect a
                                                    provider / create a project instead of
                                                    rendering blank KPI cards, if either is
                                                    still missing (e.g. Step 3 was skipped).
```

### Routing

`/onboarding` (`apps/dashboard/src/App.tsx`) — unchanged route, still standalone (no `AppLayout` sidebar/header chrome), still gated by `ProtectedRoute` only.

**New in this EP**: `ProtectedRoute`'s existing rule only ever redirected an *incomplete* user *into* `/onboarding` — it never redirected a *completed* user *out* of it if they navigated there directly (bookmark, browser back button after finishing). `Onboarding.tsx` now closes that gap itself: a `useEffect` on mount checks `user.onboarding_completed === true` and calls `navigate("/dashboard", { replace: true })`, with an accompanying early `return null` so the wizard never flashes before the redirect fires. This lives in the component rather than `ProtectedRoute` because the rule is specific to this one route ("already done, don't show it again") rather than a general auth gate — keeping `ProtectedRoute` itself unchanged from §11.

### Step 3 — Connect First Provider (rewritten this EP)

`ProviderStep` (`apps/dashboard/src/features/Onboarding.tsx`) now:
- Fetches the org's existing connections via `listProviderConnections` (same query key, `["provider-connections", organizationId]`, as `features/Connections.tsx` — so the cache is shared and a connection made here is instantly visible on the real Connections page with no extra fetch).
- Lists the same 7 providers the spec names (OpenAI, Anthropic, Google Gemini, Azure OpenAI, OpenRouter, Grok, Ollama) by importing `CONNECTABLE_PROVIDERS` from `apps/dashboard/src/lib/providerCatalog.ts` — a **new shared module**, not a new catalog: this constant (and `connectableLabel`) moved out of `features/Connections.tsx` in this EP so it could be imported without an ESLint `react-refresh/only-export-components` violation (a component file exporting non-component values breaks Fast Refresh); `Connections.tsx` re-imports it from the same place, so there is exactly one list of connectable providers, not two.
- On "Connect provider", renders `AddConnectionForm` — **imported directly from `features/Connections.tsx` and exported for this purpose**, not reimplemented. Submitting it calls the real `POST /v1/organizations/{org_id}/provider-connections` (EP-22), which encrypts the key, validates it live, and returns the connection; `onDone` (the form's existing success callback) advances the wizard to Step 4 automatically.
- "Skip for now" advances immediately with the spec's exact copy ("You can always connect providers later.") shown above the buttons, not gated behind the click.

No provider CRUD logic — request building, encryption, validation dispatch, error normalization — was rewritten; this step is entirely composed from the EP-22 component and API client.

### Empty Dashboard Improvements (new this EP)

`Overview.tsx` gained `GettingStartedBanner` (exported for testability), rendered directly under the existing `CriticalAlertBanner`:
- Queries `listProviderConnections` and `listProjectsCrud` using the **same query keys** `Connections.tsx` and `Projects.tsx` already use (`["provider-connections", orgId]` / `["projects-crud", orgId]`), so this never drifts out of sync with what those pages show and never issues a redundant network request if either page was already visited this session.
- Renders nothing once both a connection and a project exist.
- Otherwise shows one or two CTAs — "Connect your first provider" (→ `/connections`) and/or "Create your first project" (→ `/projects`) — exactly the two cases the spec names, replacing what would otherwise be a page of empty/zeroed KPI cards and charts (the existing `ChartCard`/`MetricCard` empty states, unchanged, still handle the "some data, some empty periods" case underneath this banner).
- The Projects page's own "no projects" case was **already handled** before this EP — the EP-22/EP-23 "Manage projects" section (§12) already shows an `EmptyState` with a "New project" CTA when the org has zero projects. This EP's `GettingStartedBanner` is additive (dashboard-level prompt), not a replacement for that existing, page-level empty state.

### Persistence

**Unchanged from §11** — `users.onboarding_completed_at` (nullable timestamp, migration `a3c8e21f5b7d`), `POST /v1/auth/onboarding/complete`, `UserPublic.onboarding_completed`. No new column, no new migration, no new endpoint. This EP's "only introduce a migration if absolutely necessary" instruction is satisfied by not needing one at all.

### Backend

**No backend files changed in this EP.** Every operation Step 2 (workspace rename, `PATCH /v1/organizations/{org_id}`) and Step 3 (provider connection CRUD, EP-22's `/v1/organizations/{org_id}/provider-connections*` routes) needs already existed and required no modification. The full backend test suite (1509 tests) was re-run as a regression check and passed unchanged.

### Frontend changes

- `apps/dashboard/src/features/Onboarding.tsx` — Step 3 rewritten (above), redirect-if-already-completed effect added, Finish step's secondary button relabeled "Manage providers" (from "Connect provider") to match the spec's exact button name.
- `apps/dashboard/src/features/Connections.tsx` — `AddConnectionForm` exported; `CONNECTABLE_PROVIDERS`/`connectableLabel` moved to `lib/providerCatalog.ts` (still re-exported at the same import site other code already used, so this was a non-breaking move).
- `apps/dashboard/src/lib/providerCatalog.ts` — gained `CONNECTABLE_PROVIDERS`/`connectableLabel` (moved from `Connections.tsx`, see above).
- `apps/dashboard/src/features/Overview.tsx` — `GettingStartedBanner` added (new component, exported), rendered once in the page body.

### Testing

- `apps/dashboard/src/__tests__/Onboarding.test.tsx` (new, 5 tests) — welcome step shows the user's first name; a completed session is redirected straight to `/dashboard` without the wizard ever rendering; the full Welcome→Workspace→Provider→Tour→Finish path advances correctly; Step 3's "Connect provider" button opens the real `AddConnectionForm` and a successful submit auto-advances to Tour; clicking "Go to dashboard" on Finish calls `completeOnboarding` and navigates.
- `apps/dashboard/src/__tests__/GettingStartedBanner.test.tsx` (new, 3 tests) — prompts to connect a provider when there are none; prompts to create a project when there are none; renders nothing once both exist. (Required stubbing `window.matchMedia`, since importing `features/Overview.tsx` transitively pulls in the theme store via `lib/chartPalette`, which jsdom doesn't implement — documented inline in the test file so a future test importing the same module isn't surprised by the same failure.)
- `backend/tests/test_ep21_3_onboarding.py` — unchanged, re-run as a regression check (11 tests, all passing) since no backend code in this EP touches onboarding persistence.
- Full suites: backend **1509 passed** (unchanged from EP-22, ruff/black/mypy clean); dashboard **158 passed** (150 + 8 new), lint clean, typecheck clean, build clean (`tsc -b` + `vite build`).

### Known limitations

- **Step 3's "already connected" copy is a simple count, not a list** — `ProviderStep` shows "You already have N connections" but not which providers, so a user who already connected OpenAI during a prior onboarding attempt (e.g. they refreshed mid-wizard) isn't shown that specific provider as already-done in the picker grid. Minor UX polish, not a functional gap — the actual connection is real and visible on `/connections` either way.
- **The onboarding wizard's own `AddConnectionForm` instance and the Connections page's instance are two separate mounted components** sharing a query cache, not a single shared component instance — this is the correct pattern for two different pages, but means any *future* local (non-server) state added to `AddConnectionForm` (e.g. optimistic UI) needs to work correctly when mounted from either call site, not just one.
- **`GettingStartedBanner`'s CTAs link to `/connections` and `/projects` but do not pre-open the "create" form** on arrival — a user still has to click "Add provider"/"New project" again on the destination page. Acceptable per the spec ("Do not leave empty cards" — satisfied) but a slightly smoother handoff (e.g. a `?new=1` query param the destination page reads) is easy follow-up polish, not attempted here to avoid scope creep into those pages' own state management.
- **No live, continuous browser test of the full register → onboarding (with a real provider connect) → dashboard-with-data journey** — same caveat as §9/§10/§11: verified in pieces (component tests, backend regression, builds), not as one continuous browser session, since this sandbox has no way to drive a real browser against a live deployment.

### Next milestone recommendation

Both items §13 already flagged as EP-22's own next milestone are still the highest-value work remaining and are unaffected by this EP: (1) **Settings.tsx wiring** (Priority 3, open since §12), and (2) **wiring `ProviderConnection.encrypted_api_key` into actual usage collection** so a validated connection also becomes the credential Costorah's ingestion path uses to pull real cost data — until that lands, `GettingStartedBanner` (this EP) will keep prompting even a fully-connected org, since "provider connected" and "usage data flowing" remain two different signals. That gap is worth calling out explicitly as this EP's most direct dependency on the next one.

---

## 15. EP-22.1 — Deployment Fix: Missing `cryptography` Runtime Dependency

**Status: complete.** A production deploy on Render broke after EP-22 with `ModuleNotFoundError: No module named 'cryptography'`. This is a one-line dependency-declaration fix — no application code changed.

### Root cause

EP-22 (§13) added `app/security/encryption.py`, which does `from cryptography.fernet import Fernet, InvalidToken` to implement `EncryptionService`. `cryptography` was never added to `backend/pyproject.toml`'s `[project] dependencies` list. It happened to be *installed* in this project's own dev sandbox venv only as an indirect pull-in of the dev-only `types-pyOpenSSL` stub package (confirmed via `pip show cryptography` → `Required-by: types-pyOpenSSL`), which is why the gap wasn't caught by local `pytest`/CI runs — those install `.[dev]`, which happens to transitively vendor it in by accident. A production install (`pip install -e "."`, no `dev` extras — what Render's build actually runs) never had `cryptography` at all. None of the declared production dependencies (`fastapi`, `uvicorn`, `argon2-cffi`, `PyJWT`, `httpx`, `sqlalchemy`, `alembic`, `redis`) require it either directly or transitively.

Confirmed via the deployment investigation immediately preceding this fix: `migrations/env.py` (what `alembic upgrade head` imports) never touches `cryptography`, so Alembic always succeeded regardless of this bug — only the subsequent `uvicorn app.main:app` step (which imports the provider-connections router → `ProviderCredentialService` → `EncryptionService` → `cryptography.fernet`) failed.

### Fix

`backend/pyproject.toml` — added one line to `[project] dependencies`:

```toml
# Encryption at rest — app.security.encryption.EncryptionService (EP-22
# provider-credential storage). >=44.0.0 is the first release line with
# official Python 3.13 wheels.
"cryptography>=44.0.0",
```

Placed alongside the existing Authentication group (`PyJWT`, `argon2-cffi`, `email-validator`) since it serves the same "protect user/customer secrets" purpose. `>=44.0.0` was chosen because that's the first `cryptography` release line with official prebuilt wheels for Python 3.13 (this project's `requires-python = ">=3.13"`) — an older floor would risk a source build on install. No duplicate entry existed anywhere else in `pyproject.toml` (verified by grep before and after the change — exactly one occurrence).

No application code changed — `app/security/encryption.py`'s import statement was already correct; it just needed its dependency declared.

### Testing

Reinstalled the package (`pip install -e ".[dev]"`) to pick up the new declared dependency, then re-ran the full backend gate: **1509 tests passed** (unchanged — this fix has no behavioral surface, so it couldn't and didn't change test outcomes), `ruff check` clean, `black --check` clean, `mypy app/` clean (177 source files).

### Known limitations

- This fix only corrects the dependency **declaration**. It does not, by itself, prove Render's next deploy will succeed — that also depends on Render actually building from a commit that includes this change (see the deployment investigation immediately preceding this entry for the separate, still-open question of which commit/branch Render's failing deploy was actually running).
- No dependency-completeness check (e.g. `pip check`, or a CI step that installs production-only dependencies and imports `app.main`) exists yet to catch a future "works in dev, missing in prod" gap like this one before it reaches a live deploy. Worth adding as a CI job that does `pip install -e "."` (no `dev` extra) followed by `python -c "import app.main"`.

---

## 16. EP-22.2 — Settings Backend Integration

**Status: complete.** Turns `apps/dashboard`'s Settings page from a mostly-local-state preview (explicitly labelled "This preview doesn't yet persist to the backend" on its Password tab, §9's long-standing "`Settings.tsx` doesn't persist anything to the backend despite a full save UI" gap) into six fully functional, backend-persisted sections: Profile, Workspace, Password, Preferences, API Keys, and Danger Zone. No placeholder UI remains on this page.

### Why this needed a small amount of real backend work, not just a UI pass

Auditing `app/api/v1/auth.py` and `app/api/v1/organizations.py` first (per this EP's own instruction) found: `GET /v1/auth/me` was read-only (no profile-update endpoint existed at all); no change-password endpoint existed (only the unauthenticated reset-via-email-token flow, EP-05); no account-deletion endpoint existed; `PATCH /v1/organizations/{org_id}` only accepted `name` (EP-21.3, deliberately scoped to the onboarding wizard's one field); no workspace-deletion endpoint existed; and `OrganizationApiKey` had full CRUD except rename. Every one of these gaps is a genuine "the button has nothing to call" case, not a UI polish opportunity — building the requested Settings page without them would mean fabricating success toasts over calls that don't exist, which is exactly what this project's no-fake-functionality convention (§9, §10, §12) forbids. Everything reusable *was* reused: `hash_password`/`verify_password` (unchanged from `app/auth/password.py`), `BaseRepository.update()`/`soft_delete()` (unchanged), the existing `RequirePermission`/`Permission.ORG_WRITE`/`Permission.ORG_DELETE`/`Permission.API_KEY_WRITE` RBAC dependencies (zero RBAC changes — `Permission.ORG_DELETE` already existed in the enum since EP-05 but had never been wired to an endpoint until now), and the existing `AuthService`/`OrganizationApiKeyRepository` classes (extended with new methods, not duplicated).

### Backend — Profile & Preferences (`app/api/v1/auth.py`, `app/auth/service.py`)

- **`users.preferences`** (migration `d3f6a9c8b2e4`, chained off EP-22's `c7d4f9a1b3e5`) — one nullable-free `JSONB NOT NULL DEFAULT '{}'` column on the existing `users` table. This is the EP's own "if backend persistence does not exist, implement minimal JSON storage, avoid unnecessary tables" instruction taken literally: theme, timezone, currency, date format, sidebar-collapsed, and notification toggles all live in this one free-form bag, keyed by whatever the frontend needs — no schema migration required for a future preference key. Deliberately **not** layered onto `app.models.alert.AlertPreference` (EP-19.3) — that model is scoped specifically to alert-delivery rules (quiet hours, digest cadence, severity floor), and overloading it with unrelated UI preferences (sidebar state, date format) would have been a scope violation of an existing, already-correct entity.
- **`PATCH /v1/auth/me`** (new) — partial profile update (`display_name`, `username`, `avatar_url`, `bio`, `timezone`). Uses Pydantic's `model_fields_set` (`UpdateProfileRequest`, `app/schemas/auth.py`) so a field genuinely omitted from the request body is left untouched, while a field explicitly sent as `null` clears it — the same distinction EP-22's `UpdateOrganizationRequest`-with-`exclude_unset` pattern established for the organization PATCH, applied here for the first time to `AuthService` itself (`AuthService.update_profile`). Username uniqueness reuses `UserRepository.username_exists(username, exclude_id=user.id)` (existing method, already used nowhere until now — added in EP-04 and never wired to an endpoint). Returns 409 (`UsernameAlreadyTakenError`, new exception) on collision.
- **`PATCH /v1/auth/me/preferences`** (new) — shallow-merges the given keys into `users.preferences` (`AuthService.update_preferences`). "Shallow merge, not replace" was a deliberate choice: a client changing only `theme` must not silently wipe out `notifications` set by an earlier request.
- **`UserPublic`** (`app/schemas/auth.py`) extended with `avatar_url`, `bio`, `timezone`, `created_at`, `preferences` — surfaced automatically on `/register`, `/login`, `/me`, `/onboarding/complete`, and the two new endpoints above, with zero extra plumbing (same "one schema, every auth response" pattern EP-21.3 used for `onboarding_completed`). `created_at` needs no new column — it's the existing `BaseModel` mixin timestamp, added to the response schema for the first time here to satisfy the Profile section's "Created Date" display requirement.

### Backend — Password Change (`app/auth/service.py`, `app/repositories/session_repository.py`)

- **`POST /v1/auth/change-password`** (new) — `ChangePasswordRequest{current_password, new_password}`, `CurrentUser`-authenticated. Verifies the current password with the existing `verify_password` (401 `InvalidCredentialsError` on mismatch — same exception, same status code as login), then `hash_password`s the new one (`AuthService.change_password`), identical primitives to `reset_password` (EP-05).
- **Deliberately does not sign the caller out.** `reset_password` (the existing unauthenticated recovery flow) revokes *every* session, which is correct there — the caller just proved control of the account via an emailed one-time token, not an active session, so nothing about "this session" is meaningful. An authenticated, in-session password change is different: signing the user out of the very form they used to change their password is bad UX with no security benefit. New `SessionRepository.revoke_all_for_user_except(user_id, keep_session_id)` revokes every *other* session while keeping the current one alive — the "sign out everywhere else" behavior most products give a password change, extracted as its own repository method (mirrors the existing `revoke_all_for_user`) rather than a one-off query in the service layer. The current session's id is read from the caller's own access token (`_current_session_id()`, `app/api/v1/auth.py` — mirrors `logout`'s existing header-then-cookie token extraction, reused rather than duplicated).

### Backend — Account Deletion (`app/auth/service.py`)

- **`DELETE /v1/auth/me`** (new) — `DeleteAccountRequest{password}`, password-gated (401 on mismatch, matching change-password). `AuthService.delete_account`:
  1. Verifies the password.
  2. Walks every `Membership` where the caller is `OWNER` (via the existing `MembershipRepository.list_by_user_email_with_orgs`). For each such workspace, checks whether any *other* member exists (`MembershipRepository.list_by_org_with_users`, existing). If any owned workspace has other members, the whole deletion is refused with 409 (`OwnerOfSharedWorkspaceError`, carrying the workspace name for an actionable error message) — deleting the account must never silently orphan a team workspace other people still depend on.
  3. Otherwise, every workspace the caller solely owns (including their personal workspace, which by construction — `AuthService.register` — has exactly one member) is soft-deleted (`OrganizationRepository.soft_delete`, existing method, reused), the user row itself is soft-deleted (`UserRepository.soft_delete`, inherited from `BaseRepository`, previously unused by any endpoint), and every session is revoked (`SessionRepository.revoke_all_for_user`, existing).
  4. Memberships where the caller holds a non-`OWNER` role are left untouched — soft-deleting the `User` row is sufficient to end that access (a soft-deleted user can no longer authenticate), and physically walking/removing every membership row is unnecessary work with no behavioral benefit.
- No new migration — this endpoint only mutates existing `deleted_at`/`deleted_by` columns via the pre-existing soft-delete mixin.

### Backend — Workspace (Organization) Updates (`app/api/v1/organizations.py`, `app/schemas/organizations.py`)

- **`UpdateOrganizationRequest`** extended with an optional `description` alongside the existing optional-since-this-EP `name` (previously required-`str`, now `str | None` so a description-only PATCH doesn't have to resend the name). The endpoint now applies `body.model_dump(exclude_unset=True)` to `OrganizationRepository.update()` instead of a hardcoded `name=body.name`, so it's a true partial update — the same `exclude_unset` pattern as `PATCH /v1/auth/me` above, applied consistently across both new partial-update endpoints in this EP.
- **`OrgMembershipItem`** (the response schema `GET /v1/organizations` and `PATCH /v1/organizations/{org_id}` both already returned) gained optional `description`, `is_personal`, `created_at` — all pulled from the `Organization` row's existing columns/mixin, all defaulted so every pre-existing caller of this schema is untouched.
- **`DELETE /v1/organizations/{org_id}`** (new) — `RequirePermission(Permission.ORG_DELETE)`. Because `ORG_DELETE` is present only in `_OWNER_PERMS` (`app/auth/rbac.py` — unchanged; `_ADMIN_PERMS` was never granted it), this is OWNER-only with zero new authorization logic. Refuses (400) to delete the caller's personal workspace — every account requires one (`AuthService.register`'s invariant) — otherwise soft-deletes via the existing `OrganizationRepository.soft_delete`.

### Backend — API Key Rename (`app/api/v1/organizations.py`, `app/schemas/organization_api_keys.py`)

- **`UpdateApiKeyRequest{name?, description?}`** (new schema) + **`PATCH /v1/organizations/{org_id}/api-keys/{key_id}`** (new endpoint, `Permission.API_KEY_WRITE` — the same permission `POST`/`DELETE` on this resource already require, ADMIN+OWNER only). Deliberately does **not** accept `permissions`, `expiration`, or the key material — matching `ProviderConnection`'s EP-22 precedent (rotation is a distinct, separately-logged action from renaming), scope/expiry changes mean issuing a new key, not mutating an old one.

### Frontend (`apps/dashboard`)

- **`services/api.ts`** — `updateProfile`, `updatePreferences`, `changePassword`, `deleteAccount`, `updateApiKey`, `deleteOrganization`; `updateOrganization`'s signature changed from `(id, name: string)` to `(id, {name?, description?})` (its one existing caller, `Onboarding.tsx`'s workspace-rename step, updated to `{ name: newName }` — source-compatible, no behavior change there).
- **`types/backend.ts`** — `BackendUserPublic` gained `avatar_url`/`bio`/`timezone`/`created_at`/`preferences`; `BackendOrgMembershipItem` gained optional `description`/`is_personal`/`created_at`.
- **`stores/auth.ts`** — `AuthUser` gained the same five fields as optional, following the exact "absent means unknown, not false" precedent `onboarding_completed` already established for sessions persisted before a field existed (self-heals on the next `/me` refresh, same as EP-21.3 documented).
- **`components/ConfirmDialog.tsx`** — gained an optional `children` slot rendered between the description and the action buttons, so the Danger Zone's account-deletion dialog can collect a password inline without a second, bespoke modal component. Existing callers (unaffected — no caller passed `children` before) are source- and behavior-compatible.
- **`features/ApiKeys.tsx`** — refactored to export `ApiKeysManager({ compact })`, containing everything the standalone `/api-keys` page used to render inline (list, create dialog, revoke confirmation) plus new rename support (edit icon → a small `Dialog`-based rename form, wired to the new `updateApiKey`). The standalone page is now `<PageHeader/> + <ApiKeysManager/>`; Settings' API Keys section renders `<ApiKeysManager compact />` (hides the permissions/expiry columns to fit a tab panel, keeps name/prefix/created/last-used + actions). This mirrors the `AddConnectionForm` extraction EP-21.3 already established for provider connections — one implementation, two mount points, not two copies of the create/rename/revoke logic Section 5 of this EP's spec explicitly forbade duplicating.
- **`features/Settings.tsx`** — fully rewritten. The prior version (8 tabs: Profile/Appearance/Notifications/Security/Organization/Data/Billing/API) was largely local-`useState`, Zustand-only, or explicitly-labelled preview UI (`PreviewBadge`, "This preview doesn't yet persist to the backend"). The new version has exactly the six sections this EP's spec named:
  - **Profile** — display name, username, avatar URL (all editable via `PATCH /v1/auth/me`), read-only email/status/member-since, bio. Optimistic-feeling save via TanStack Query mutation + a 2.5s "Saved!" state, matching the existing save-button convention used elsewhere in the app (`ApiKeys.tsx`, the old Settings).
  - **Workspace** — name and description (editable, `PATCH /v1/organizations/{id}`), slug and organization ID (read-only — slugs are assigned once at registration and intentionally never editable, per EP-21.3's original design note, still true), a "Personal workspace" badge, created-date.
  - **Password** — current/new/confirm, zod-validated (min length, confirmation match), `POST /v1/auth/change-password`; a 401 from a wrong current password surfaces as "Incorrect password" via the shared `apiErrorMessage` mapper.
  - **Preferences** — theme (three-way, unchanged mechanism from `stores/theme.ts`, now also persisted to `users.preferences.theme`), currency, sidebar-collapsed, timezone, date format, and four notification toggles — every change fires `PATCH /v1/auth/me/preferences` immediately (no separate "Save" button; toggle-style prefs save on interaction, matching how the theme switcher already behaved pre-EP). Reads via a small `pref(preferences, key, fallback)` helper so an unset key falls back to a sensible default rather than `undefined`.
  - **API Keys** — `<ApiKeysManager compact />` (see above) — real create/rename/copy-prefix/revoke, reusing EP-14's existing scoped-permission and expiration model exactly as it already worked on `/api-keys`.
  - **Danger Zone** — "Delete Workspace" (blocked with an explanatory message, not just a disabled button, for the personal workspace; otherwise `ConfirmDialog` → `DELETE /v1/organizations/{id}`) and "Delete Account" (`ConfirmDialog` with the new inline password field → `DELETE /v1/auth/me`; a 409 "sole owner of a shared workspace" error surfaces the specific workspace name from the backend's error detail, not a generic failure).
- **A real bug found and fixed during this EP, not pre-existing behavior changed for its own sake**: the original `TextField` helper (both in the old Settings.tsx and initially copied into the new one) was a plain function component, not `React.forwardRef`. Spreading `react-hook-form`'s `register(...)` return value onto it meant the `ref` callback React silently drops when passed as a prop to a non-forwardRef component — so `react-hook-form` could never attach to the real `<input>`, and thus could never apply `defaultValues` to it on mount (RHF sets `defaultValue` via the ref callback, not via a `value`/`defaultValue` prop). Every text field on the old Settings page — Profile's display name/username/email/bio, the Password tab's three fields — was therefore *rendering visually empty on first load* regardless of the user's actual data, only ever getting a value once the user typed into it themselves. This had no test coverage before this EP (no `Settings.test.tsx` existed), so it went uncaught. Fixed by converting `TextField` to `forwardRef<HTMLInputElement, ...>` and forwarding the ref to the underlying `<input>` — verified by `Settings.test.tsx`'s very first assertion (`getByDisplayValue("Ada Lovelace")` on initial render, which failed before the fix and passes after). `TextField` also gained an auto-derived `htmlFor`/`id` pair (from the label text, or an explicit `id` prop) — the old version had no programmatic label association at all, an accessibility gap independent of the ref bug, fixed in the same pass since both surfaced through the same component.

### Testing

- **Backend** (`backend/tests/test_ep22_2_settings.py`, 36 new tests): `AuthService.update_profile` (partial updates, explicit-null clears, omitted-field-untouched, username-taken, keep-own-username), `update_preferences` (shallow merge, key overwrite), `change_password` (wrong password, success re-hashes + revokes-others-not-self, no-password-hash-account), `delete_account` (wrong password, sole-owner-of-shared-workspace blocked, solo-owner deletes org+account, non-owner membership left alone); HTTP layer for `PATCH /v1/auth/me` (success, 409 taken username, 401 unauthenticated), `PATCH /v1/auth/me/preferences` (merge, 401), `POST /v1/auth/change-password` (success, 401 wrong password, 422 short new password, 401 unauthenticated), `DELETE /v1/auth/me` (204, 401 wrong password, 409 shared workspace, 401 unauthenticated), `PATCH /v1/organizations/{id}` description-only update, `DELETE /v1/organizations/{id}` (owner 204, admin 403, personal-workspace 400, 401 unauthenticated), `PATCH /v1/organizations/{id}/api-keys/{key_id}` (admin renames, member 403, cross-org key 404, 401 unauthenticated). `tests/conftest.py`'s `make_user`/`make_org` factories extended with the new EP-22.2 fields (`avatar_url`/`bio`/`timezone`/`preferences`/`created_at` on `make_user`; `description`/`is_personal`/`created_at` on `make_org`) — these are plain transient ORM objects that never pass through a session flush, so the model's column-level `default=`/`server_default=` never apply to them without the factory setting them explicitly; this is what let `test_ep05.py`'s pre-existing `UserPublic` construction test and `test_ep21_3_onboarding.py`'s `/me`-serialization tests keep passing unmodified in behavior, just updated to supply the now-required fields. Full backend suite: **1545 passed** (1509 + 36), ruff/black/mypy clean.
- **Frontend**: `ApiKeys.test.tsx` extended with 1 new test (rename flow, both mocked and asserted against the real `updateApiKey` call shape) — 7 total, all passing, none of the prior 6 changed in intent. `Settings.test.tsx` (new, 11 tests): default Profile view renders the real user's data (the regression test for the forwardRef bug above), profile save calls `PATCH /v1/auth/me` with the right payload, workspace save calls `PATCH /v1/organizations/{id}` with name+description, password change succeeds and shows a persisted-looking success state, password mismatch is caught client-side before any network call, a preference toggle persists via `PATCH /v1/auth/me/preferences` with the full merged notification-preferences object (this test also caught and drove the fix for a second real bug — see below), the API Keys section renders the shared `ApiKeysManager`, personal-workspace deletion is blocked in the UI, workspace deletion calls `DELETE /v1/organizations/{id}` after confirmation, account deletion requires a password before confirming, and account deletion calls `DELETE /v1/auth/me` with the supplied password once one is given. **A second real bug found via this test, not a test-only fix**: `onToggleNotification` computed its "existing notifications" value with an empty-object fallback (`pref(preferences, "notifications", {})`) instead of reusing the already-defaulted `notificationPrefs` the same render computed for display — so toggling one notification setting (e.g. "Weekly digest") would have silently dropped every other notification preference (budget/anomaly/security) the next time preferences were saved, even though the UI displayed them as still on. Fixed by computing the defaults once and having both the render and the toggle handler read the same value. Full dashboard suite: **170 passed** (158 + 1 ApiKeys rename + 11 Settings), lint clean, typecheck clean, build clean (`tsc -b` + `vite build`).

### API endpoints added

| Method | Path | Auth |
|---|---|---|
| PATCH | `/v1/auth/me` | `CurrentUser` (self) |
| PATCH | `/v1/auth/me/preferences` | `CurrentUser` (self) |
| POST | `/v1/auth/change-password` | `CurrentUser` (self) |
| DELETE | `/v1/auth/me` | `CurrentUser` (self), password-gated |
| DELETE | `/v1/organizations/{org_id}` | `Permission.ORG_DELETE` (OWNER only) |
| PATCH | `/v1/organizations/{org_id}/api-keys/{key_id}` | `Permission.API_KEY_WRITE` (ADMIN+OWNER) |

`PATCH /v1/organizations/{org_id}` (pre-existing, EP-21.3) is extended, not new — now accepts `description` alongside `name`, both optional/partial.

### Known limitations

- **Account deletion's "sole owner of a shared workspace" check is all-or-nothing per request** — a user who owns three workspaces, two solo and one shared, is blocked from deleting their account entirely rather than being offered "delete the two solo ones and keep the account until the shared one is resolved." This matches the spec's "no accidental deletion" requirement (nothing is deleted unless everything can be) but is stricter than a partial-deletion UX might be; not attempted here to avoid a confusing multi-step deletion flow.
- **No email confirmation step for account/workspace deletion** — password re-entry is the only confirmation gate (matching the spec's "require confirmation dialog," which this satisfies), not a second-channel (email link) confirmation some products add for irreversible actions. Worth considering if account deletion abuse becomes a real concern.
- **Preferences are validated by nothing beyond "is it JSON"** — the backend accepts any `dict[str, Any]` patch; a client could in principle write an arbitrary key. This is an accepted tradeoff of the "avoid unnecessary tables" JSON-blob approach and mirrors how flexible preference bags work in comparable products; if a preference key ever needs server-side business logic (not just display), it should graduate to a real column at that point, not be validated inside the JSON blob.
- **Workspace deletion does not yet cascade-warn about what will be lost** — the confirmation copy says "projects, connections, API keys, and members" generically; it does not fetch and display actual counts (e.g. "3 projects, 12 API calls this month") the way some products do before a destructive action. The backend soft-deletes the `Organization` row itself (existing `passive_deletes=True` relationships mean child rows are not walked by this endpoint) — functionally correct (a soft-deleted organization's children become unreachable through the normal API surface, matching the standing soft-delete convention, DP-7) but not yet a proven cascade audit.
- **No live, continuous browser test of the full Settings flow** — same caveat as every prior EP (§9, §10, §11, §14): verified in pieces (backend endpoint tests, frontend component tests, both full builds), not as one continuous browser session, since this sandbox has no way to drive a real browser against a live deployment.

### Next milestone recommendation

With Settings now fully wired, the two items §12/§13/§14 have been carrying forward as "the next real blocker" are unaffected by this EP and remain the highest-value work: (1) **wiring `ProviderConnection.encrypted_api_key` into actual usage collection** (EP-16's ingestion path and the SDK-facing `get_usage()` calls), and (2) the still-open **transactional email** gap (EP-25 in the §8 roadmap) — which would also let account/workspace deletion gain the email-confirmation step this EP's "Known limitations" flagged as a reasonable future hardening, once outbound email exists to send it through.

---

## 17. EP-22.3 — Intelligent Dashboard Empty States & Guided First Experience

**Status: complete.** Replaces the dashboard's generic "No data for this period" placeholders with a 4-state setup-progress machine and contextual, actionable empty states — a brand-new organization now sees guidance toward its next concrete action instead of blank charts. Zero new backend endpoints; every signal is derived from three already-existing endpoints.

### Why no backend changes were needed

This EP's own instruction was "avoid new endpoints unless absolutely required." Auditing what "has this org connected/validated/used anything" actually needs turned up nothing missing: `GET /v1/organizations/{id}/provider-connections` already returns `last_validation_status` per connection (EP-22, §13) — the exact signal needed to distinguish "provider exists" from "provider validated"; `GET /v1/organizations/{id}/projects` already returns a count; and `GET /v1/dashboard/overview` already answers "how much usage occurred in [start, end]" — querying it with a fixed, far-past `start_date` (`2020-01-01`, predating the product's own existence) turns it into an honest "has this org ever recorded any usage" check without adding any new backend surface area. No migration, no schema change, no new router — this EP is 100% frontend.

### Dashboard State Machine (`apps/dashboard/src/hooks/useDashboardState.ts`, new)

```
state 1 — no provider connected           → hasConnections is false
state 2 — provider(s) exist, none validated → hasConnections true, hasValidatedConnection false
state 3 — validated, but no usage ever     → hasValidatedConnection true, hasUsage false
state 4 — usage exists                     → render the full dashboard, unchanged
```

`useDashboardState()` composes three TanStack Query calls:
- `listProviderConnections` — **same query key** (`["provider-connections", organizationId]`) `features/Connections.tsx` and the EP-21.3/EP-22 onboarding step already use, so this hook's cache is always the one true copy, never a second fetch drifting out of sync.
- `listProjectsCrud` — same reuse pattern, same query key as `features/Projects.tsx`.
- `getOverview({ start_date: "2020-01-01", end_date: today })` — a **distinct** query key (`["overview-all-time", organizationId]`) from the date-range-scoped `["overview", ...]` key `hooks/useDashboard.ts`'s `useOverview()` already uses for the KPI cards, since this one is intentionally range-independent and only used for state detection, not display.

`hasValidatedConnection` checks `connections.some(c => c.last_validation_status === "healthy")` — the fine-grained per-connection signal EP-22 (§13) introduced specifically to distinguish "a credential is stored" from "a credential was proven to work," which is exactly the state-2-vs-state-3 boundary this EP needed.

### Component architecture (`apps/dashboard/src/features/Overview.tsx`)

- **`GettingStartedBanner`** (rewritten in place, same export name — Overview.tsx's one call site is unchanged) — supersedes EP-21.3's 2-item version with the full 5-step checklist the spec names: Connect Provider, Validate Provider, Create Project, Generate AI Usage, View Analytics. Each row shows a check/circle icon, strikes through once done, and shows a "Go" link to the relevant page only while incomplete. "Generate AI Usage" and "View Analytics" both read `hasUsage` — Overview.tsx *is* the analytics view, so once usage exists there is nothing further to detect; a separate "has visited /analytics" flag would have been exactly the kind of duplicate client-side progress state this EP's own instructions forbid. Renders `null` once all 5 items are done, matching the EP-21.3 predecessor's "disappear when done" behavior.
- **`DashboardStateHero`** (new, exported) — renders the state-1/2/3 copy verbatim from the spec (title, body, bullet list for state 3, primary/secondary CTAs) directly under the checklist; returns `null` for state 4, letting the KPI cards and charts underneath carry the page on their own exactly as before this EP.
- **`SpendTrendEmpty` / `ProviderDistributionEmpty` / `TopModelsEmpty`** (new, internal to Overview.tsx) — passed into `ChartCard`'s new `emptyContent` prop (see below) so each chart's empty state matches the spec's per-card copy instead of the generic "No data for this period." `ProviderDistributionEmpty` lists the same 7 providers `CONNECTABLE_PROVIDERS` (`lib/providerCatalog.ts`, EP-21.3/EP-22) already names — reused, not a second hardcoded list.
- **Provider Snapshot section and `LiveActivityFeed`** are now gated on `dashboardState.state === 4` — an empty stats grid or an empty activity feed under a hero that already says "waiting for requests" would be redundant blank space, so these sections simply don't mount until there's something in them to show.

### `ChartCard` extension (`apps/dashboard/src/components/ChartCard.tsx`)

Added one new optional prop, `emptyContent?: ReactNode`. When `empty` is true and `emptyContent` is provided, it fully replaces the default `ChartEmpty` (icon + "No data for this period" + generic message) — every other `ChartCard` call site in the app that doesn't pass this prop is byte-for-byte unaffected, verified by the full existing test suite passing unmodified. This is a general-purpose extension (any chart anywhere can now supply contextual empty guidance), not an Overview-only hack.

### Empty-state strategy

| Chart | Condition | Content |
|---|---|---|
| Spend Trend | state 1 (no providers) | "Start tracking AI spend. Connect your first provider." + Connect Provider button |
| Spend Trend | state 2/3 (provider connected, no usage) | "Waiting for AI usage. Charts will automatically appear..." |
| Provider Distribution | `!hasConnections` | "No providers connected." + the 7 supported-provider chips + Add Provider button |
| Top Models | `topModels.length === 0` (any state) | "Your highest-cost AI models will appear here automatically once requests are recorded." |
| Token Throughput | unchanged | Spec didn't name a contextual variant for this chart — left on `ChartCard`'s existing generic empty message. |

### Testing

- **Backend**: none — no endpoint was added, so per this EP's own instruction ("Backend: only if new endpoint is added") no backend test changes were made. Full backend suite re-verified unchanged (1545 passed) as a regression check.
- **Frontend**:
  - `src/__tests__/GettingStartedBanner.test.tsx` (rewritten, 5 tests — supersedes the EP-21.3 2-test version, which tested behavior this EP intentionally replaced): all 5 steps render unchecked for a brand-new org; Connect Provider checks off once a connection exists (and its own "Go" link disappears while Validate Provider's remains); Validate Provider checks off once a connection's `last_validation_status` is `"healthy"`; Generate AI Usage and View Analytics both check off together once `total_requests > 0`; the whole banner renders nothing once all 5 are done.
  - `src/__tests__/DashboardStateHero.test.tsx` (new, 4 tests — one per state): state 1 shows "Welcome to Costorah" with Connect Provider (linking to `/connections`) and Learn More; state 2 shows "Provider connected" with Validate Connection; state 3 shows "Everything is ready." with the 5-item bullet list (token usage, model usage, request count, spending, trends) and View Providers; state 4 renders nothing.
  - Full dashboard suite: **176 passed** (170 + 5 rewritten GettingStartedBanner + 4 new DashboardStateHero, net +6 from the prior EP's 170), lint clean, typecheck clean, build clean (`tsc -b` + `vite build`). No pre-existing test needed changes beyond the intentionally-rewritten `GettingStartedBanner.test.tsx`.

### Known limitations

- **"Has usage ever" is computed via a wide-range query, not a true unbounded one.** `ALL_TIME_START = "2020-01-01"` is a safe lower bound (predates Costorah's own existence) rather than an actual "since account creation" query — functionally equivalent for every real account, but if the backend's `GET /v1/dashboard/overview` is ever changed to reject very old `start_date` values, this constant would need to move with it. A dedicated `has_usage: bool` field on a future summary endpoint (if one is ever justified by other needs) would remove this assumption entirely.
- **The all-time usage check adds one extra request per Overview page load** (`["overview-all-time", ...]`) beyond the existing date-range-scoped overview query. It's cached for 5 minutes and only runs once per organization per session in practice, but it is a real additional network call — the tradeoff this EP's own "if one lightweight summary endpoint improves performance, implement it" clause anticipated; not built here because the added latency is negligible (a single indexed aggregate query) and the reuse-over-new-endpoint instruction was the stronger signal.
- **Provider Distribution's contextual empty state only covers the "no providers" case.** When a provider is connected but has no usage yet (state 2/3), the pie chart falls back to `ChartCard`'s generic empty message rather than a second bespoke variant — the spec's Analytics Cards section only specified copy for the "no providers" case for this particular chart.
- **No live, continuous browser test of the full state-1-through-4 journey** — same caveat as every prior EP (§9, §10, §11, §14, §16): verified in pieces (component tests per state, full build), not as one continuous browser session driving a real account from zero through to its first usage event, since this sandbox has no way to drive a real browser against a live deployment.

### Next milestone recommendation

Unchanged from §16 — this EP was purely a frontend guidance/empty-state pass and doesn't move either of the two standing highest-value backend items: (1) wiring `ProviderConnection.encrypted_api_key` into actual usage collection (the thing that would make state 3 → state 4 happen for real accounts, not just demo/test data), and (2) transactional email. Once (1) lands, this EP's state machine is what will make that transition visibly obvious to a user for the first time — the "Everything is ready. Waiting for your applications to send AI requests." message becomes literally true rather than aspirational.

---

## 18. EP-24 — Authorization & Permission Consistency Audit

**Status: complete.** A full audit of every authorization surface (backend routers/dependencies/RBAC, frontend action buttons, database ownership columns) triggered by one reported inconsistency: a MEMBER could create a Project but not delete it. The audit found **exactly one** genuine bug — that one — fixed it, and confirmed every other resource's permission set is already internally consistent. No new tables, no new permissions, no new API surface — this EP is a one-line grant plus its regression tests and documentation.

### Root cause

`app/auth/rbac.py`'s `_MEMBER_PERMS` granted `Permission.PROJECT_WRITE` but not `Permission.PROJECT_DELETE`. This was never a deliberate security decision — `app/api/v1/projects.py`'s own module docstring already claimed *"granted to every role down to VIEWER for read and MEMBER+ for write/delete"*, directly contradicted by the permission grant it sat above. The code disagreed with its own documentation, which is the strongest available signal that this was an oversight (most likely: PROJECT_DELETE was added to the `Permission` enum and to `_ADMIN_PERMS`/`_OWNER_PERMS` in EP-13, but the corresponding `_MEMBER_PERMS` entry was never added when EP-23's Projects CRUD API actually started using it).

The frontend was never the problem: `apps/dashboard/src/features/Projects.tsx`'s `ProjectCrudRow` already renders an unconditional Delete button (`aria-label="Delete project"`) for every project — the button existed and would have looked functional to a MEMBER, silently 403'ing on click before this fix. This is the general failure mode a backend-only permission gap produces: since **no page in `apps/dashboard` performs any client-side role-based UI gating** (confirmed by an app-wide audit below), every action button is always rendered for every authenticated member of the org, and the backend's `RequirePermission` dependency is the only enforcement point. That's an intentional, consistent architecture (see "Frontend audit" below) — it just means a backend permission gap always manifests as a broken *action*, never a missing *button*.

### Audit method

1. Read `app/auth/rbac.py` (the single source of truth for role → permission grants) and enumerated every `Permission` value.
2. For each resource with both a WRITE-shaped and a DELETE-shaped permission (`PROJECT_*`, `PROVIDER_*`), checked whether every role holding the WRITE permission also holds the DELETE permission.
3. For resources with only one mutating permission (`API_KEY_WRITE` covers create/rename/revoke; `NOTIFICATION_WRITE` covers acknowledge/resolve/dismiss/reopen/preferences), confirmed there is no create/delete split to audit — a single permission gating the whole mutation surface can't itself be inconsistent.
4. Cross-checked every backend router (`app/api/v1/*.py`) against `app/auth/rbac.py` to confirm the `RequirePermission(Permission.X)` annotation on each endpoint matches the permission the resource's docstring/design intends (this is what caught the Projects docstring/grant mismatch).
5. Audited `apps/dashboard/src/features/*.tsx` for every action button (Create/Edit/Rename/Delete/Test/Activate/Rotate/Copy) named in the task, confirming each has a corresponding rendered control and a corresponding backend endpoint — no missing buttons, no orphaned buttons calling endpoints that don't exist.
6. Audited the database layer: confirmed every mutable resource (`Organization`, `Project`, `ProviderConnection`, `OrganizationApiKey`) is scoped by `organization_id` (multi-tenant boundary) and gated exclusively by `Membership.role` via `RequirePermission` — never by a `created_by`/ownership column. `Project` has no `created_by` column at all; `OrganizationApiKey.created_by` exists but is audit metadata only (nullable, `ON DELETE SET NULL`), never read by any authorization check (`grep`-confirmed no `created_by`/`deleted_by` comparison anywhere in `app/auth/`). This is a deliberate, consistent design choice already documented implicitly across EP-13/EP-14/EP-22/EP-23: Costorah's authorization model is **role-based within an organization, not per-creator ownership** — any MEMBER can already edit/rename a project or connection someone else on the team created, so extending that same role (not creator identity) to delete is the consistent choice, not a new concept.

### Complete permission matrix (post-fix)

| Resource | Action | Permission | VIEWER | MEMBER | ADMIN | OWNER |
|---|---|---|:---:|:---:|:---:|:---:|
| Organization (Workspace) | Read | `ORG_READ` | ✅ | ✅ | ✅ | ✅ |
| Organization (Workspace) | Rename / description | `ORG_WRITE` | ❌ | ❌ | ✅ | ✅ |
| Organization (Workspace) | Invite / change role / remove member | `ORG_MANAGE_MEMBERS` | ❌ | ❌ | ✅ | ✅ |
| Organization (Workspace) | Delete | `ORG_DELETE` | ❌ | ❌ | ❌ | ✅ |
| Project | Read / list | `PROJECT_READ` | ✅ | ✅ | ✅ | ✅ |
| Project | Create / rename / update | `PROJECT_WRITE` | ❌ | ✅ | ✅ | ✅ |
| Project | **Delete** | `PROJECT_DELETE` | ❌ | **✅ (fixed — was ❌)** | ✅ | ✅ |
| Provider Connection | Read / list | `PROVIDER_READ` | ✅ | ✅ | ✅ | ✅ |
| Provider Connection | Create / rename / activate / deactivate / rotate key / test | `PROVIDER_WRITE` | ❌ | ❌ | ✅ | ✅ |
| Provider Connection | Delete | `PROVIDER_DELETE` | ❌ | ❌ | ✅ | ✅ |
| API Key | Read / list | `API_KEY_READ` | ✅ | ✅ | ✅ | ✅ |
| API Key | Create / rename / revoke / copy (client-only, no perm) | `API_KEY_WRITE` | ❌ | ❌ | ✅ | ✅ |
| Usage | Read (dashboard) | `USAGE_READ` | ✅ | ✅ | ✅ | ✅ |
| Usage | Write (ingestion, M2M only — not a dashboard action) | `USAGE_WRITE` | ❌ | ❌ | ✅ | ✅ |
| Billing | Read / write (not yet implemented — EP-27) | `BILLING_READ`/`BILLING_WRITE` | ❌ | ❌ | ✅ (read) / ✅ | ✅ |
| Alerts / Notifications | Read | `NOTIFICATION_READ` | ✅ | ✅ | ✅ | ✅ |
| Alerts / Notifications | Acknowledge / resolve / dismiss / reopen / preferences | `NOTIFICATION_WRITE` | ❌ | ✅ | ✅ | ✅ |
| Profile (self) | Edit / change password / delete account | *(none — `CurrentUser` identity, not role)* | ✅ | ✅ | ✅ | ✅ |
| Preferences (self) | Read / update | *(none — `CurrentUser` identity, not role)* | ✅ | ✅ | ✅ | ✅ |
| Budgets | *(no separate resource — `Project.budget` is a field, edited via `PROJECT_WRITE`)* | — | — | — | — | — |

Bold row is the one cell this EP changed. Every other cell was already correct and is now covered by a regression test (`tests/test_ep24_authz_audit.py`).

### Backend endpoints audited

Every `RequirePermission(...)`/`RequireMembershipOrApiKeyPermission(...)` annotation in `app/api/v1/organizations.py`, `app/api/v1/projects.py`, `app/api/v1/provider_connections.py`, `app/api/v1/auth.py`, `app/api/v1/alerts.py`, and `app/api/v1/rbac.py` was read and cross-checked against `app/auth/rbac.py`'s grants. Only `projects.py`'s `DELETE /{project_id}` endpoint's declared permission (`PROJECT_DELETE`) disagreed with what its own docstring said MEMBER should be able to do — every other endpoint's permission annotation already matched its resource's intended role boundary.

### Frontend actions audited

| Page | Actions checked | Result |
|---|---|---|
| `features/Projects.tsx` | Create, Rename, Delete | All three buttons present and unconditional (no client-side role gating anywhere in the app — see below) |
| `features/Connections.tsx` | Create, Rename, Delete, Activate/Deactivate, Rotate key, Test connection | All six present |
| `features/ApiKeys.tsx` (`ApiKeysManager`, shared with Settings' API Keys tab — EP-22.2) | Create, Rename, Copy prefix, Revoke | All four present |
| `features/Settings.tsx` | Workspace rename/description/delete, Profile edit, Password change, Account delete, Preferences read/update | All present (EP-22.2) |

**No missing buttons, no orphaned buttons.** Confirmed via `grep` across `apps/dashboard/src` that no component reads a membership role to conditionally hide/disable an action — every page shows every action to every authenticated org member and lets the backend's 403 (surfaced via the app's existing `apiErrorMessage`/`toast.error("Not allowed", ...)` pattern, used consistently since EP-14) be the enforcement signal. This is architecturally consistent and was not changed by this EP — flagged only as a known limitation below (a nicer UX would grey out actions a VIEWER/MEMBER can't perform, rather than let them fail), not a correctness bug: the backend is always the actual authority, so no button here can grant an action the backend would refuse.

### Database ownership audit

- `Project`, `ProviderConnection`, `OrganizationApiKey`, `Membership` are all scoped by `organization_id` (`ForeignKey("organizations.id", ondelete="CASCADE")`) — the multi-tenant boundary every `RequirePermission`-gated endpoint enforces via `_get_current_membership`/`ensure_org_membership` before any permission check runs.
- No resource's authorization depends on a `created_by`/owner column. `Project` has none. `OrganizationApiKey.created_by` exists (nullable FK, `ON DELETE SET NULL`) but is audit-trail metadata only — confirmed by reading every call site that touches it (`app/api/v1/organizations.py`'s `create_api_key`) and confirming no `RequirePermission`/service-layer check ever compares it to the caller's id.
- `deleted_by` (the `BaseModel` soft-delete mixin column) is populated inconsistently across routers — `AuthService.delete_account`/`OrganizationApiKeyRepository.delete` pass it explicitly, while `app/api/v1/organizations.py`'s org-delete, `app/api/v1/projects.py`'s project-delete, and `app/api/v1/provider_connections.py`'s connection-delete call `repo.soft_delete(x)` with no `deleted_by` argument. This is an audit-trail completeness gap, not an authorization gap (`deleted_by` is never read by any permission check), and is noted under "Known limitations" rather than fixed here to keep this EP scoped to the permission-consistency rule it was asked to enforce.

### Fixes applied

- **`app/auth/rbac.py`** — added `Permission.PROJECT_DELETE` to `_MEMBER_PERMS`. One line, reusing the existing `Permission` enum and `RequirePermission` dependency exactly as they already work for every other endpoint — no new permission, no hardcoded role check, no duplicated authorization logic anywhere.
- **`app/auth/rbac.py`** (documentation) — added an explicit comment block above `_OWNER_PERMS` recording the audit's consistency invariant and its one deliberate exception (`ORG_DELETE` stays OWNER-only despite ADMIN holding `ORG_WRITE`, because deleting a workspace cascades to every project/connection/key/member it owns — categorically more destructive than any other delete in the table, and mirrors the existing "only an OWNER may grant the OWNER role" precedent already in `app/api/v1/organizations.py`). This turns a previously-implicit design decision into a documented one, satisfying the task's "unless there is a documented security reason" clause going forward.
- **`tests/test_ep23_projects.py`** — removed the now-stale docstring on `test_admin_can_delete` that asserted "only ADMIN/OWNER can [delete]" (no longer true), added `test_member_can_delete` as the direct regression test for the fix.
- No frontend code changed — the Delete button already existed; it simply started working once the backend permission was granted.

### Testing

- **`backend/tests/test_ep24_authz_audit.py`** (new, 12 tests):
  - `TestPermissionConsistencyInvariant` — a parametrized, table-driven test asserting **for every role**, WRITE implies DELETE for both audited WRITE/DELETE pairs (`PROJECT_*`, `PROVIDER_*`). This is the audit's rule encoded as an executable guardrail — any future resource that adds a `_SOMETHING_WRITE`/`_SOMETHING_DELETE` pair to `_WRITE_DELETE_PAIRS` gets this consistency check for free, and any regression (like the one this EP fixed) fails the suite immediately instead of waiting for another manual bug report.
  - `TestProjectDeleteGrantedToMember` — pins the concrete fix (MEMBER has both `PROJECT_WRITE` and `PROJECT_DELETE`; VIEWER still has neither).
  - `TestProviderConnectionsRemainConsistent` — confirms Provider Connections were already consistent (MEMBER has neither WRITE nor DELETE, a matched pair) and locks that in, so a future change can't silently create the Projects-style gap there.
  - `TestApiKeyWriteCoversRenameAndDelete` — confirms the single-permission-covers-everything design for API keys is intact.
  - `TestOrganizationDeleteDocumentedException` — pins the one deliberate exception (`ORG_DELETE` OWNER-only) so it can't silently widen or narrow without a corresponding update to the comment in `rbac.py`.
  - `TestRolePermissionsMonotonic` — sanity check that `ROLE_PERMISSIONS` still forms a strict hierarchy (OWNER ⊇ ADMIN ⊇ MEMBER ⊇ VIEWER) after the fix.
- **`backend/tests/test_ep23_projects.py`** — added `test_member_can_delete` (MEMBER deletes a project successfully, 204, `soft_delete` called once); removed the stale docstring on `test_admin_can_delete`. `test_viewer_cannot_delete` (pre-existing) is unchanged and still passes.
- Full backend suite: **1560 passed** (1545 + 12 new EP-24 tests + 3 net-new in `test_ep23_projects.py`'s delete class), ruff/black/mypy clean.
- **Frontend**: no code changed, so no new tests were required by this EP's own "Testing: Backend — only if new endpoint is added" precedent (extended here to "no frontend change → no new frontend test"); the existing `Projects.test.tsx`/`ManageProjectsSection.test.tsx` suite (EP-22/EP-23) was re-run as a regression check and passed unchanged, confirming the Delete button's existing behavior (calls `deleteProject`, shows a confirm dialog, invalidates the query on success) is untouched by this EP.

### Known limitations

- **No client-side permission-aware UI anywhere in `apps/dashboard`.** Every action button is always rendered for every authenticated org member regardless of role; a VIEWER sees the same Delete/Rename/Create buttons a MEMBER does and only discovers they can't act via the 403 toast. This is a UX polish opportunity, not a security gap (the backend is the sole authority), but a role-aware `useCurrentMembership()`/`useHasPermission(Permission.X)` hook — reading the `role` field `GET /v1/organizations` already returns per org — would let the frontend greyed out or hide actions a role definitely cannot perform, closing the loop the way the RBAC introspection endpoints (`GET /v1/rbac/roles`, `/permissions`, EP-13) were originally built to support. Not built here to keep this EP scoped to the permission-consistency rule it was asked to audit and fix, not a new frontend capability.
- **`deleted_by` is populated inconsistently across delete endpoints** (see "Database ownership audit" above) — an audit-trail completeness gap, never an authorization gap, left unfixed to keep this EP scoped.
- **The "future resources" review is a documented convention, not an enforced one.** `_WRITE_DELETE_PAIRS` in `test_ep24_authz_audit.py` must be manually extended whenever a new resource gains a WRITE/DELETE permission pair — there's no automatic discovery of new `Permission` enum members that would need pairing. A stronger version of this guardrail (deriving `_WRITE_DELETE_PAIRS` automatically from every `*_WRITE`/`*_DELETE` naming convention in the `Permission` enum) was considered and deliberately not built, to avoid the parametrized test silently changing behavior/scope every time an unrelated permission is added to the enum for a reason that has nothing to do with create/delete symmetry (e.g. `BILLING_WRITE`, which has no corresponding `BILLING_DELETE` concept at all).

### Remaining authorization improvements

1. **Frontend permission-awareness** (see "Known limitations") — the single highest-value follow-up: a shared `useHasPermission()` hook so buttons reflect what a role can actually do, rather than relying entirely on 403-after-click.
2. **`deleted_by` consistency** — thread `current_user.id` through every `soft_delete()` call site that doesn't already pass it, for complete audit trails.
3. Everything else this session's earlier EPs already flagged as the next real product blockers is unaffected by this audit and remains true: wiring `ProviderConnection.encrypted_api_key` into real usage collection, and transactional email (§17).

---

## 19. EP-23.3 — AI Usage Synchronization Engine

**Status: complete.** Closes the loop every prior EP since §13 has flagged as "the next real blocker": a validated, encrypted `ProviderConnection` credential (EP-22) now actually pulls usage data, not just proves reachability. No dashboard analytics were added or changed by this EP — that is explicitly out of scope, reserved for a future EP built on top of the data this engine now writes.

### Why this needed almost no new infrastructure

Auditing the existing codebase first (per this EP's own instruction) found that EP-08 had already built the entire usage-collection pipeline — `UsageCollectionService` (pagination, checkpointing, normalization, persistence), `UsageCollectionRun`/`UsageCollectionCheckpoint` models and repositories, retry-on-transient-failure via `ProviderHttpClient`/`ExponentialRetryPolicy` — but wired it only to server-side environment-variable credentials, never a customer's own connected, encrypted credential. Building a second collection pipeline for customer credentials would have been exactly the kind of duplicated business logic this EP was explicitly told not to write. Instead, `UsageCollectionService.collect()` gained one optional parameter (`config: ProviderConfig | None`) so a caller can inject an already-built, connection-derived `ProviderConfig` instead of the function's original env-var lookup — every other line of pagination/checkpoint/normalization/persistence logic is untouched and still shared by both the env-var-keyed ops path (`app/api/v1/usage.py`, unchanged) and the new customer-credential path below.

### Architecture

```
ProviderConnection (encrypted_api_key, EP-22)
        │
        ▼
ProviderCredentialService.decrypt()      — same EP-22 service; decrypts only
        │                                   in memory, for this one call
        ▼
build_provider_config()                  — app/providers/validation.py,
        │                                   promoted from private _build_config
        │                                   to a public function EP-22's
        │                                   ProviderValidator and this EP's
        │                                   ProviderSyncService both call —
        │                                   one place builds a ProviderConfig
        │                                   from a decrypted key, not two
        ▼
UsageCollectionService.collect(config=…) — EP-08, unchanged except for the
        │                                   optional config parameter above;
        │                                   still owns pagination, the
        │                                   provider adapter's retry-capable
        │                                   HTTP client, normalization
        │                                   (NormalizerRegistry), dedup
        │                                   upsert, and checkpoint advance
        ▼
UsageCollectionRun (+ UsageCollectionCheckpoint, UsageEvent, UsageCostRecord)
        │
        ▼
ProviderSyncService.get_sync_status()    — derives "sync status" fields
                                            entirely from the rows above;
                                            nothing new is persisted for
                                            status tracking
```

`ProviderSyncService` (`app/services/provider_sync_service.py`, new) is the thin orchestration layer requested by this EP's "reusable synchronization service" requirement — it does not reimplement anything EP-08 or EP-22 already does; it composes them.

### Sequence diagram — manual sync of one connection

```
Frontend            API router              ProviderSyncService        ProviderCredentialService   UsageCollectionService        Provider
   │  POST .../sync     │                          │                          │                          │                      │
   ├───────────────────►│                          │                          │                          │                      │
   │                    │  sync_connection(conn)   │                          │                          │                      │
   │                    ├─────────────────────────►│                          │                          │                      │
   │                    │                          │  decrypt(encrypted_key)  │                          │                      │
   │                    │                          ├─────────────────────────►│                          │                      │
   │                    │                          │◄─────────────────────────┤ plaintext (memory only)  │                      │
   │                    │                          │  build_provider_config() │                          │                      │
   │                    │                          │  collect(config=cfg)     │                          │                      │
   │                    │                          ├──────────────────────────┼─────────────────────────►│  get_usage() (paged) │
   │                    │                          │                          │                          ├─────────────────────►│
   │                    │                          │                          │                          │◄─────────────────────┤
   │                    │                          │                          │                          │  normalize + upsert  │
   │                    │                          │                          │                          │  advance checkpoint  │
   │                    │                          │◄─────────────────────────┼──────────────────────────┤  UsageCollectionRun  │
   │                    │  get_sync_status(conn)    │  (COMPLETED or FAILED)  │                          │                      │
   │                    │◄─────────────────────────┤                          │                          │                      │
   │◄───────────────────┤  TriggerSyncResponse      │                          │                          │                      │
```

A failed provider call never reaches the frontend as a 500: `UsageCollectionService.collect()` persists a `FAILED` `UsageCollectionRun` (existing EP-08 behavior) and re-raises; `ProviderSyncService.sync_connection()` catches that specific exception, re-fetches the just-persisted `FAILED` run via the new `UsageCollectionRunRepository.get_latest_for_connection()`, and returns it as a normal terminal result. Only a genuinely unexpected exception (e.g. a database error) propagates past this layer.

### `ProviderSyncService` (`app/services/provider_sync_service.py`, new)

- **`sync_connection(organization_id, connection, triggered_by=MANUAL, lookback_days=30)`** — syncs one connection. Always returns a terminal `UsageCollectionRun` (`COMPLETED` or `FAILED`), never raises for a provider-side failure.
- **`sync_all_connections(organization_id, ...)`** — syncs every active connection in an org (via the pre-existing `ProviderConnectionRepository.list_active_by_org`). One connection's failure never stops the others — each is awaited in turn and every outcome is included in the returned list.
- **`get_sync_status(organization_id, connection)`** — read-only, no side effects. Returns a `SyncStatus` dataclass derived from: the latest `UsageCollectionRun` (any status, for "last sync started/completed" and "last error"), the latest `COMPLETED` run (for "last successful sync"), the `UsageCollectionCheckpoint` (for "last imported timestamp"), and new all-time aggregate queries on `UsageEvent`/`UsageCostRecord` (for records/tokens/cost imported).
- **Manual vs. incremental**: every call is "manual" in the sense that this EP wires no scheduler (see "Known limitations"), but the *date range* requested from the provider is always incremental — `_effective_start()` resumes from `UsageCollectionCheckpoint.last_collected_at` when one exists and is within the lookback window, otherwise falls back to a bounded `DEFAULT_LOOKBACK_DAYS = 30` window rather than requesting a provider's entire history on every call.
- **Unsupported providers are honest, not faked.** Only `openai` and `anthropic` have a real `get_usage()` implementation as of this EP (`_PRODUCTION_USAGE_PROVIDERS`, mirroring §13's `_PRODUCTION_PROVIDERS`/`_PRODUCTION_USAGE_PROVIDERS` distinction for the other 5 named providers). Syncing one of the other 5 records an honest, zero-events `COMPLETED` run with an explanatory `error_message` — never a fabricated import, never a hard error the user can't act on. `SyncStatus.supports_usage_sync` surfaces this to the frontend so the UI can disable "Sync now" with an explanation instead of letting the user retry a call that can never succeed.

### Retry strategy — reused, not rebuilt

This EP's retry requirements (retry transient failures, never retry authentication failures) were already fully satisfied by EP-06/EP-07's `ProviderHttpClient` (`app/http/client.py`) and `ExponentialRetryPolicy` (`app/http/retry.py`), which retry every individual provider HTTP request based on `ProviderError.retryable` flags (`app/providers/errors.py`):

| Exception | `retryable` | Retried? |
|---|---|---|
| `RateLimitError` | `True` | Yes |
| `NetworkError` | `True` | Yes |
| `InternalProviderError` | `True` | Yes |
| `AuthenticationError` | `False` | No |
| `QuotaExceededError` | `False` | No |
| `InvalidRequestError` | `False` | No |

No new retry code was written. A whole *sync run* that still fails after those per-request retries is simply left in `FAILED` status with the normalized error captured — the user's own "Sync Now" click (or a future scheduled retry, which is just "call sync again") naturally resumes from the last checkpoint. A separate retry-scheduling subsystem was deliberately not built, since nothing in this EP's scope requires unattended background retries (see "Known limitations" on scheduling).

### Database — no migration

Every "sync status" field this EP's spec requested (Last Sync Started, Last Sync Completed, Last Successful Sync, Last Error, Last Imported Timestamp, Sync Status) is derived entirely from existing rows: `UsageCollectionRun` (EP-08) already records `started_at`/`completed_at`/`status`/`error_message`/`events_collected`/`events_failed`; `UsageCollectionCheckpoint` (EP-08) already records `last_collected_at`. Two new **read** methods were added, no new columns and no migration:

- `UsageCollectionRunRepository.get_latest_for_connection(org_id, connection_id, status=None)` — the connection-scoped counterpart to the existing provider-scoped `get_latest_for_provider`.
- `UsageEventRepository.get_totals_by_connection(connection_id)` — all-time record/token counts, counted from `UsageEvent` (created for every collected event) rather than `UsageCostRecord` (created only when a price match exists) so the total is never undercounted by a missing price.
- `UsageCostRecordRepository.get_totals_by_connection(connection_id)` — all-time cost totals grouped by currency (mirrors the existing `get_totals_by_org`'s currency-grouping pattern, but lifetime rather than period-scoped).

### API — 3 new endpoints, all on the existing EP-22 router

No new router file. `app/api/v1/provider_connections.py` (EP-22) gained three endpoints, reusing its existing `_get_owned_connection` helper and `PROVIDER_READ`/`PROVIDER_WRITE` permissions verbatim — no RBAC changes:

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/v1/organizations/{org_id}/provider-connections/{id}/sync-status` | `PROVIDER_READ` | Read-only derived sync status |
| POST | `/v1/organizations/{org_id}/provider-connections/{id}/sync` | `PROVIDER_WRITE` | Manually sync one connection |
| POST | `/v1/organizations/{org_id}/provider-connections/sync` | `PROVIDER_WRITE` | Manually sync every active connection in the org |

`PROVIDER_WRITE` is ADMIN+OWNER only (unchanged from EP-22, §13) — a MEMBER can view sync status but not trigger a sync, matching the existing test/rotate endpoints' authorization boundary exactly.

New schemas (`app/schemas/provider_connections.py`): `SyncStatusResponse`, `SyncRunResponse`, `TriggerSyncResponse`, `SyncAllResponse`, `CostImportedItem`. `estimated_cost_imported` costs are serialized as strings (not floats) to avoid float-precision loss across the API boundary, matching how monetary values are handled elsewhere in this codebase.

### Security

Identical guarantees to EP-22's credential handling (§13 Part 7), because this EP calls the same `ProviderCredentialService.decrypt()` and never introduces a second decryption path: the plaintext key exists only as a Python local for the duration of one `sync_connection()` call, is never logged (structlog calls in `provider_sync_service.py` bind only `provider`/`organization_id`/`connection_id`/timing/counts — never the exception message itself, which is logged only as `error_type=type(exc).__name__`), never returned in any API response, and never persisted anywhere in plaintext. `SyncRunResponse.error_message` and `SyncStatusResponse.last_error` both come from `UsageCollectionRun.error_message`, which EP-08's own exception handling already populates from `str(exc)` on the *provider adapter's* exception hierarchy — the same hierarchy EP-22's `ProviderValidator` already established never interpolates credential material into its messages.

### Frontend (`apps/dashboard/src/features/Connections.tsx`)

Each connection row (`ConnectionRow`) gained a new `SyncStatusPanel` subsection, and the section header gained a "Sync all" action:

- **Sync status badge** — one of Never synced / Pending / Syncing… / Synced / Sync failed (`SYNC_STATUS_BADGE`, mirrors the existing `HEALTH_BADGE`/`VALIDATION_LABELS` pattern already used for EP-22's validation status).
- **Last sync timestamp**, **records imported**, **tokens imported**, **estimated cost imported** (formatted per-currency via `Intl`-backed `toLocaleString`), and **last error** — all sourced from `GET .../sync-status`, fetched via its own React Query key (`["provider-connection-sync-status", organizationId, connectionId]`) so it caches and invalidates independently of the connection list itself.
- **"Sync now"** — calls `POST .../sync`, writes the response's `sync_status` directly into the query cache (`queryClient.setQueryData`) so the panel updates immediately without a second round-trip, and toasts success/failure with the records-imported count or the normalized error. Disabled (with an inline explanation) when `supports_usage_sync` is `false`.
- **"Refresh status"** — refetches `GET .../sync-status` on demand, satisfying this EP's explicit "Refresh Status" button requirement independent of triggering a new sync.
- **"Sync all"** (section-level, next to "Add provider") — calls `POST .../sync`, invalidates both the connections list and every connection's sync-status query, and toasts a summary (`"Synced N of M connections"` or a warning if some failed). Hidden when the org has no connections yet, matching the page's existing empty-state convention.

New API client functions in `apps/dashboard/src/services/api.ts`: `getProviderConnectionSyncStatus`, `syncProviderConnection`, `syncAllProviderConnections`, plus the `SyncStatusResponse`/`SyncRunResponse`/`TriggerSyncResponse`/`SyncAllResponse`/`CostImportedItem` types mirroring the new backend schemas exactly.

### Testing

- **Backend** (`backend/tests/test_ep23_3_usage_sync.py`, 22 new tests): `ProviderSyncService.sync_connection` (unsupported-provider honest zero-events run, supported-provider success path with decrypted-config verification, Ollama's no-credential path never calling `decrypt()`, failure re-fetches the persisted `FAILED` run instead of raising, failure re-raises when no run can be found at all, and 4 `_effective_start` incremental-date-range cases: no checkpoint, recent checkpoint, stale checkpoint beyond the lookback window, and a checkpoint in the future); `sync_all_connections` (one failure doesn't stop others, empty org returns an empty list); `get_sync_status` (never-synced, full derivation with totals, unsupported-provider flag); API-level tests for all 3 new endpoints covering 200/401/403/404 and the RBAC boundary (VIEWER can read but not sync, MEMBER can read but not sync — `PROVIDER_WRITE` is ADMIN+OWNER only — ADMIN can sync), plus an explicit assertion that no ciphertext ever appears in a sync response body. Full backend suite: **1582 passed** (1560 + 22), ruff/black/mypy clean.
- **Frontend** (`apps/dashboard/src/__tests__/ManageConnectionsSection.test.tsx`, extended with 8 new tests in a new `describe` block): never-synced display, full success-state display (status badge, records/tokens/cost imported), failed-sync display with the last error message, "Sync now" triggering `syncProviderConnection` and updating the panel from the response, "Sync now" disabled with an explanation for a provider that doesn't support usage sync yet, "Refresh status" re-fetching sync status, "Sync all" triggering `syncAllProviderConnections`, and "Sync all" not rendering when the org has no connections. The pre-existing 9 EP-22 tests in this file were updated only to add a default `getProviderConnectionSyncStatus` mock (since every connection row now mounts a `SyncStatusPanel`) — no existing assertion changed. Full dashboard suite: **184 passed** (176 + 8), lint clean, typecheck clean (`tsc -b`), build clean.

### Known limitations

- **No scheduler.** This EP builds the synchronization *engine* and its manual trigger, exactly as scoped ("Implement endpoint(s) allowing users to trigger synchronization... manually") — it does not wire a cron/background scheduler to call `sync_all_connections` automatically. `app/usage/background.py`'s `BackgroundCollectionFramework` (EP-08) remains dormant and unwired, as it has been since EP-08 — using it would require new app-lifecycle/session-factory plumbing beyond this EP's stated scope ("Only implement the synchronization engine"). Automatic/scheduled sync is the natural next step once this engine has been exercised manually.
- **Execution is synchronous, within the HTTP request.** `POST .../sync` runs the full provider fetch inline and returns once it completes, matching the existing "Test Connection"/"Rotate Key" precedent (EP-22, §13) rather than returning an immediate "202 Accepted" and polling for completion. For the 30-day, single-connection lookback window this EP defaults to, this is an acceptable latency tradeoff consistent with the rest of this router; a long-history backfill or very large orgs calling "Sync all" across many connections would be the trigger to revisit this as a background job (see "No scheduler" above — the same missing piece would resolve both).
- **Only 2 of 7 named providers (OpenAI, Anthropic) have a real `get_usage()`** — unchanged from EP-06/EP-07/§13; syncing the other 5 is honest and zero-cost (a fast, correct `COMPLETED` run) but imports nothing. Extending a provider's usage sync support requires only implementing that provider's adapter `get_usage()` (EP-06/EP-07's existing per-provider extension point) and adding it to `_PRODUCTION_USAGE_PROVIDERS` — no change to `ProviderSyncService`, the API, or the frontend.
- **No live, continuous browser test of a real end-to-end sync** — same caveat as every prior EP in this document: verified in pieces (backend unit/API tests with mocked HTTP transports, frontend component tests, both full builds), not as one continuous browser session against a live provider, since this sandbox has no way to drive a real browser against a live deployment or hold a real provider credential.

### Next milestone recommendation

With the synchronization engine now real, the two natural follow-ups are: (1) a **scheduler** (cron-triggered `sync_all_connections` across every organization, likely reusing `app/usage/background.py`'s dormant framework or a simpler periodic-task runner) so usage data flows without a user manually clicking "Sync now" — this is what would finally make §17's `GettingStartedBanner`/`DashboardStateHero` state-3-to-state-4 transition ("Everything is ready. Waiting for your applications to send AI requests.") happen automatically for a connected, validated provider; and (2) **dashboard analytics on top of the newly-flowing data** — explicitly out of scope for this EP by its own instruction, but now unblocked now that `UsageEvent`/`UsageCostRecord` rows exist for customer-connected providers, not just env-var-keyed ops usage.

---

## 20. EP-23.4 — Background Usage Synchronization Scheduler

**Status: complete.** Closes §19's own "next milestone recommendation" #1: usage now flows into the dashboard without any user clicking "Sync now" — a per-organization background scheduler periodically calls the exact same `ProviderSyncService` EP-23.3 built, on a configurable interval (5m/15m/1h/6h/24h). No dashboard analytics were added by this EP either — still deliberately out of scope, per §19's #2.

### Why this is a new, thin component rather than an extension of an existing one

This EP's own instruction was "use the existing background framework if already present; extend it; if none exists, implement the minimum necessary." Auditing `app/usage/background.py`'s `BackgroundCollectionFramework` (EP-08) found it *looks* like the obvious thing to extend but isn't actually a scheduler: it has no notion of an interval or "check what's due" — it only exposes `submit()` for one explicit, caller-triggered collection run, tracked in an in-memory task registry. Two more specific problems ruled out wrapping it rather than just not using it:

1. **Session factory signature mismatch.** `BackgroundCollectionFramework.__init__` expects `session_factory: Callable[[], Awaitable[AsyncSession]]` — an async callable that directly returns an open session (`session = await self._session_factory()`). Every other non-request call site in this codebase, including `app.api.deps.get_db` and `AppContainer.session_factory` itself, uses the opposite shape: `async_sessionmaker[AsyncSession]`, called synchronously and used via `async with session_factory() as session:`. `AppContainer.session_factory` cannot be passed to `BackgroundCollectionFramework` as-is — it was never actually wired to the container this session confirmed (§19 and earlier already flagged it as "dormant, unwired").
2. **Wrong call path.** `BackgroundCollectionFramework._run_task` calls `UsageCollectionService` directly with an env-var-keyed config — it has no idea `ProviderSyncService` (EP-23.3) or per-connection encrypted credentials exist. Making it credential-aware would mean rewriting its one method, at which point it would no longer be "the existing framework," just a class with the same name.

So `BackgroundCollectionFramework` is left exactly as EP-08/EP-23.3 documented it — dormant, untouched, a plain manual-task tracker still available for a future one-off use. The new `UsageSyncScheduler` (`app/services/usage_sync_scheduler.py`) is the "minimum necessary" scheduler: it owns *when* to sync (interval math, concurrency, locking) and delegates *how* entirely to `ProviderSyncService.sync_all_connections()` — one new call site, zero duplicated collection/retry/provider logic.

### Architecture

```
UsageSyncScheduler                — WHEN: tick loop, per-org interval, concurrency/locking (new, EP-23.4)
        │
        ▼
ProviderSyncService.sync_all_connections()   — WHICH connections, credential decrypt (EP-23.3, reused unchanged)
        │
        ▼
UsageCollectionService.collect()  — HOW: pagination/normalization/persistence/checkpoint (EP-08, reused unchanged)
        │
        ▼
ProviderHttpClient + ExponentialRetryPolicy  — per-request retry of transient failures (EP-06/EP-07, reused unchanged)
        │
        ▼
UsageCollectionRun (+ UsageCollectionCheckpoint, UsageEvent, UsageCostRecord)  — persisted, unchanged schema
```

### Scheduler lifecycle

`UsageSyncScheduler` is constructed once in `AppContainer.create()` (`app/core/container.py`), alongside the engine/session-factory/Redis/event-bus/connection-manager it already builds, and started automatically (`settings.scheduler_enabled`, default `True`) right after `connection_manager.start()`. `AppContainer.close()` stops it before disposing the engine/Redis. A new `SettingsDep`-style dependency, `SchedulerDep` (`app/api/deps.py`'s `get_usage_sync_scheduler`), exposes it to routers the same way `EventBusDep`/`ConnectionManagerDep` already do; it raises 503 rather than crashing if a container was ever built without one (only `tests/test_ep19_1.py`'s hand-built `_mock_container()` does this, since `AppContainer.usage_sync_scheduler` is an `Optional` field precisely so that pre-EP-23.4 test helper didn't need updating).

```
AppContainer.create()
        │
        ├─ engine, session_factory, redis  (unchanged)
        ├─ connection_manager.start()       (unchanged)
        │
        ├─ usage_sync_scheduler = UsageSyncScheduler(session_factory, redis=redis,
        │       tick_interval_seconds=settings.scheduler_tick_interval_seconds)
        └─ if settings.scheduler_enabled: await usage_sync_scheduler.start()
                        │
                        ▼
                asyncio.create_task(_run_loop())
                        │
              ┌─────────┴─────────┐
              │  loop forever:     │
              │  await tick()      │
              │  await sleep(N)    │   N = scheduler_tick_interval_seconds (default 60s;
              └────────────────────┘       SCHEDULER_TICK_INTERVAL_SECONDS env var, 10–3600s)
```

`tick()` never runs organization-specific work itself — it discovers due organizations and fires off `_run_job()` as an independent `asyncio.create_task` per organization, so one organization's slow provider doesn't delay the next tick's discovery pass or another organization's dispatch.

### Sequence diagram — one tick, one due organization

```
Scheduler loop          UsageSyncScheduler         Redis            ProviderSyncService        UsageCollectionRun table
     │  sleep elapses          │                     │                      │                          │
     ├─────────────────────────►  tick()             │                      │                          │
     │                         │  OrganizationRepository.list_auto_sync_enabled()                        │
     │                         │  (orgs.sync_settings->>'auto_sync_enabled' = 'true')                    │
     │                         │  for each org:       │                      │                          │
     │                         │  UsageCollectionRunRepository.get_latest_for_org(org, SCHEDULED)         │
     │                         │◄─────────────────────┼──────────────────────┼──────────────────────────┤
     │                         │  due = now >= last_run.completed_at + interval  (or True if never run)  │
     │                         │  skip if org already in _running_org_ids (in-process guard)              │
     │                         │  SET scheduler:lock:org:{id} NX EX ttl                                   │
     │                         ├─────────────────────►│                      │                          │
     │                         │◄─────────────────────┤ OK / already-locked  │                          │
     │                         │  (skip if lock not acquired)                │                          │
     │                         │  asyncio.create_task(_run_job(job))         │                          │
     │                         │           │           │                      │                          │
     │                         │           ▼           │                      │                          │
     │                         │  job.status = RUNNING │                      │                          │
     │                         │  sync_all_connections(org, triggered_by=SCHEDULED)                       │
     │                         │           ├──────────────────────────────────►                          │
     │                         │           │           │            decrypt + build_provider_config       │
     │                         │           │           │            + UsageCollectionService.collect()    │
     │                         │           │           │            (per connection, EP-23.3 unchanged)   │
     │                         │           │           │                      ├──────────────────────────►│
     │                         │           │◄──────────┼──────────────────────┤ [UsageCollectionRun, ...] │
     │                         │  job.status = COMPLETED / FAILED (any connection FAILED -> job FAILED)   │
     │                         │  DEL scheduler:lock:org:{id}                 │                          │
     │                         ├─────────────────────►│                      │                          │
```

### Concurrency model

Two independent, layered guards — the same "defense in depth, degrade gracefully" pattern this codebase already uses for login rate limiting (`app.auth.rate_limit`):

1. **In-process** (`UsageSyncScheduler._running_org_ids: set[UUID]`) — checked before any I/O, for free. Covers the common single-worker deployment and prevents a slow-running org from being re-dispatched by the next tick before it finishes.
2. **Cross-process** (Redis `SET scheduler:lock:org:{org_id} NX EX <ttl>`, `ttl = clamp(interval_seconds, 60, 86400)`) — reuses the exact same `redis.asyncio.Redis` client already on `AppContainer`, no new infrastructure. If Redis is unreachable, `_acquire_lock` catches the exception and returns `True` (allowed) rather than blocking sync — a Redis outage narrows the safety net to the in-process guard only, it never stops background sync from running. This mirrors `app.auth.rate_limit._RedisBackend`'s own documented fallback philosophy verbatim.

A `max_concurrent_orgs` `asyncio.Semaphore` (default 5) additionally bounds how many organizations sync *simultaneously within one process* — a large backlog of simultaneously-due organizations queues (`SchedulerJobStatus.QUEUED` until the semaphore admits it) rather than firing every job at once.

**What this does not claim to be**: a distributed job queue with exactly-once delivery guarantees across an arbitrary number of workers. It is "safe" in the sense the spec asked for — duplicate synchronization is prevented, not merely made unlikely — but it is a lock, not a queue; a worker that dies mid-job holds its Redis lock until the TTL (bounded by the org's own sync interval) expires, at which point the next tick's `_is_due` check (driven by the *persisted* last-run timestamp, not the lock) picks it back up. See "Known limitations" for the corresponding startup-storm caveat.

### Checkpoint / due-detection flow

**No new checkpoint logic** — `UsageSyncScheduler` never touches `UsageCollectionCheckpoint` directly; that remains entirely `UsageCollectionService`'s responsibility (EP-08), reused unchanged via `ProviderSyncService`. What the scheduler *does* own is "due detection," and it is deliberately stateless across restarts:

```
_is_due(org_id, interval_seconds):
    latest = UsageCollectionRunRepository.get_latest_for_org(org_id, triggered_by=SCHEDULED)
    if latest is None:            → due = True   (initial sync)
    else:
        next_run = latest.completed_at + interval_seconds
        due = now >= next_run     → (incremental sync, resume after interruption,
                                      recovery after deployment restart — all the
                                      same code path, because "due" is always
                                      recomputed from the database, never from
                                      in-memory state that a restart would lose)
```

Because every tick re-derives "when did this org last run" from the `UsageCollectionRun` table rather than from any process-local timestamp, a deployment restart (the scheduler's in-memory `_jobs`/`_running_org_ids` reset to empty) does not cause organizations to be silently skipped or double-synced on the first post-restart tick — it just re-evaluates the same due-check against the same durable data it always would have.

### Retry flow — fully reused, zero new retry code

Identical to EP-23.3's own retry section (§19), because this EP calls the same `ProviderSyncService.sync_connection()`/`sync_all_connections()` and introduces no second retry path: `ProviderHttpClient` + `ExponentialRetryPolicy` (EP-06/EP-07) retry each individual provider HTTP request based on `ProviderError.retryable`:

| Failure | Retried by the existing HTTP layer? |
|---|---|
| Timeout / `NetworkError` | Yes |
| 429 / `RateLimitError` | Yes |
| Temporary provider outage / `InternalProviderError` | Yes |
| Invalid API key / `AuthenticationError` | No |
| Unsupported provider | N/A — `ProviderSyncService` records an honest zero-events `COMPLETED` run, never attempts the call (EP-23.3) |
| Revoked credentials → `AuthenticationError` | No |

The scheduler's own `retry_count` field (surfaced in the API/UI, see below) is **not** an HTTP retry counter — threading a per-request retry count out of `ProviderHttpClient` up through `UsageCollectionService`/`ProviderSyncService` into the scheduler would mean modifying an internal that this EP was explicitly told not to touch. Instead it counts **consecutive scheduler-job failures for that organization**, derived from the scheduler's own in-memory job history (`_consecutive_failure_streak`) — "this org's background sync has failed N ticks in a row," a genuinely different and equally useful signal, disclosed as such in both the API response and this doc rather than conflated with HTTP-level retries.

### Database — one new column, no new tables

Per this EP's "avoid new tables whenever possible; only add minimal schema if scheduler settings require persistence" instruction: `organizations.sync_settings` (migration `e8f1a2b3c4d5`, chained off EP-22.2's `d3f6a9c8b2e4`) — a single `JSONB NOT NULL DEFAULT '{}'` column, the exact same "minimal JSON bag, no dedicated table" pattern EP-22.2 established for `users.preferences` (§16). Holds exactly two keys: `{"auto_sync_enabled": bool, "interval_seconds": int}`. A missing key means "not configured" (auto sync off, default interval) — not a stored `false`/default — so every pre-existing organization needs no backfill and is correctly treated as opted-out.

- `OrganizationRepository.list_auto_sync_enabled(limit, cursor)` (new) — cursor-paginated query filtering `status = ACTIVE AND sync_settings->>'auto_sync_enabled' = 'true'` directly in SQL (JSONB `.astext` comparison), not loaded-then-filtered in Python.
- `UsageCollectionRunRepository.get_latest_for_org(org_id, triggered_by=None, status=None)` (new) — the org-wide counterpart to EP-23.3's connection-scoped `get_latest_for_connection`; an org can have many connections, and the scheduler needs "when did *any* connection in this org last get a SCHEDULED run," not a per-connection answer.

`UsageCollectionRun`/`UsageCollectionCheckpoint` themselves are completely unchanged — every "sync status" field the scheduler surfaces (last sync, next sync, records imported) is derived the same way EP-23.3's `SyncStatusResponse` already was, just aggregated at the organization level instead of per-connection.

### API — 3 new endpoints, still on the existing EP-22/EP-23.3 router

No new router file; no duplicate of the EP-23.3 sync endpoints. `app/api/v1/provider_connections.py` gained:

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/v1/organizations/{org_id}/provider-connections/scheduler/status` | `PROVIDER_READ` | Auto-sync config + last/next sync + process-wide monitoring counters, in one call |
| PATCH | `/v1/organizations/{org_id}/provider-connections/scheduler/settings` | `PROVIDER_WRITE` | Enable/disable auto-sync, set interval (partial update, `exclude_unset`-equivalent — only supplied fields change) |
| GET | `/v1/organizations/{org_id}/provider-connections/scheduler/jobs` | `PROVIDER_READ` | Recent scheduler job history for this org (queued/running/completed/failed, duration, records imported, retry count) |

`PROVIDER_WRITE` is ADMIN+OWNER only (unchanged RBAC boundary from EP-22/EP-23.3) — a MEMBER can see whether auto-sync is on and watch it run, but cannot turn it on or change the interval, matching every other provider-connection mutation in this router. These three literal path segments (`/scheduler/status`, `/scheduler/settings`, `/scheduler/jobs`) coexist without ambiguity alongside the existing `/{connection_id}/...` parametrized routes — verified via the app's own generated OpenAPI schema (`app.openapi()["paths"]`), not just by inspection, since Starlette route matching is order- and arity-sensitive and this was worth confirming directly rather than assuming.

New schemas (`app/schemas/provider_connections.py`): `SchedulerStatusResponse`, `SchedulerJobItem`, `SchedulerJobsResponse`, `SchedulerMonitoringSnapshot`, `UpdateSchedulerSettingsRequest` (accepts the interval as one of the 5 literal labels — `"5m"|"15m"|"1h"|"6h"|"24h"` — never a raw second count, so an invalid interval can never be persisted via the API even though the scheduler's own `interval_seconds_for()` also clamps defensively at read time).

### Security

Identical guarantees to EP-22 (§13 Part 7) and EP-23.3 (§19): the scheduler never introduces a second decryption path — `ProviderSyncService.sync_connection()` (unchanged) is the only place a plaintext key is ever produced, and only in memory, for the duration of one connection's sync. `UsageSyncScheduler`'s own structlog calls bind only `job_id`/`organization_id`/timing/counts — a job failure is logged as `error_type=type(exc).__name__`, never `str(exc)`, matching `ProviderSyncService`'s existing convention exactly. No scheduler API response includes credential material (`SchedulerStatusResponse`/`SchedulerJobItem` carry no connection-level fields at all — that's still `SyncStatusResponse`'s job, EP-23.3). Redis lock keys (`scheduler:lock:org:{org_id}`) contain only a UUID, never a credential or org name.

### Performance

- `list_auto_sync_enabled` filters `auto_sync_enabled`/`status` in the SQL `WHERE` clause, not in Python — orgs that haven't opted in are never loaded.
- `_is_due` is one indexed query per organization per tick (`UsageCollectionRun` is already indexed on `organization_id` + `started_at`, EP-08) — no N+1 across connections, since due-detection is org-level, not per-connection.
- No duplicate provider authentication: `ProviderSyncService.sync_all_connections()` already decrypts and authenticates once per connection per sync (EP-23.3, unchanged) — the scheduler adds no additional auth round-trip on top of that.
- Redis lock acquire/release is two round-trips (`SET NX EX`, `DEL`) per dispatched job, not per tick — organizations that aren't due this tick never touch Redis at all.
- The scheduler's own tick cadence (`scheduler_tick_interval_seconds`, default 60s) is independent of any org's configured sync interval, so a fleet of orgs all set to "daily" doesn't mean 1440 idle due-checks between real work — each due-check is a cheap indexed query, not a source of meaningful load at the scale this product operates at today.

### Frontend

**Connections page** (`apps/dashboard/src/features/Connections.tsx`) — new `AutoSyncStatusSection`, rendered above the existing "Your provider connections" section: Auto Sync Enabled/Disabled badge + configured interval, a scheduler-health badge (Healthy/Degraded/Disabled/Not running — `SCHEDULER_HEALTH_BADGE`, mirrors the existing `HEALTH_BADGE`/`SYNC_STATUS_BADGE` vocabulary rather than inventing a new one), "Last sync"/"Next sync" timestamps, and — when a job is in flight or just finished — its status/records-imported/duration/retry-count. Polls `GET .../scheduler/status` every 20s (`refetchInterval`) so a background sync that completes without any user action is reflected without a manual page refresh (the "dashboard refresh" requirement); when the polled `current_job` transitions to `completed`/`failed`, a `useEffect` invalidates the existing `["provider-connections", ...]` and `["provider-connection-sync-status", ...]` query keys — **reusing** EP-23.3's own query-invalidation, not introducing a parallel refresh mechanism. Manual "Sync now"/"Sync all" buttons (EP-23.3) are untouched and still present.

**Settings page** (`apps/dashboard/src/features/Settings.tsx`) — new `AutomaticSyncCard`, added to the **Workspace** tab (not Preferences, which is per-user `users.preferences` — auto-sync is an organization-wide setting shared by every member, exactly like the workspace name/description already on that tab). An ON/OFF switch and a 5-option interval `<select>` (5m/15m/1h/6h/24h), each firing `PATCH .../scheduler/settings` immediately on change (no separate Save button, matching how the pre-existing theme/notification toggles in this same file already behave), plus read-only "Last sync"/"Next sync"/"Scheduler: {health}" text.

New API client functions/types in `apps/dashboard/src/services/api.ts`: `getSchedulerStatus`, `updateSchedulerSettings`, `getSchedulerJobs`, plus `SchedulerStatusResponse`/`SchedulerJobItem`/`SchedulerJobsResponse`/`SchedulerMonitoringSnapshot`/`SchedulerInterval` types mirroring the new backend schemas exactly.

### Testing

- **Backend** (`backend/tests/test_ep23_4_scheduler.py`, 34 new tests): pure-function interval helpers (clamping, label round-trip); `tick()`/`_maybe_dispatch` (dispatches a due org and calls `sync_all_connections` with `triggered_by=SCHEDULED`, skips a not-yet-due org, skips orgs `list_auto_sync_enabled` itself already filtered out, skips an org already in `_running_org_ids`, skips when the Redis lock is held elsewhere, degrades to "allowed" when Redis raises, always allows when no Redis is configured); job execution (`_run_job` success and failure paths, a partial per-connection failure still marks the whole job FAILED, `retry_count` reflects the consecutive-failure streak and resets after a success); due-detection (never-synced is always due, a recent run is not due, a stale run beyond the interval is due — the deployment-restart-recovery case); `get_org_status`/`monitoring_snapshot` derivation; `start()`/`stop()` lifecycle (idempotent, no leaked task); API-level tests for all 3 new endpoints (200/401/403/404, the ADMIN-can/VIEWER-and-MEMBER-cannot `PROVIDER_WRITE` boundary on the settings PATCH). `tests/conftest.py`'s `_make_mock_container` and `make_org` factories extended (a real, unstarted `UsageSyncScheduler` on the mock container; `sync_settings` on the org factory) — same "transient ORM object needs every field the code now reads" precedent EP-22.2 already established for `preferences`/`description`/`is_personal`. Full backend suite: **1616 passed** (1582 + 34), ruff/black/mypy clean.
- **Frontend**: `ManageConnectionsSection.test.tsx` gained a new `describe` block (3 tests: disabled state, enabled state with interval/next-sync/health, in-flight job status/records/duration/retry-count) plus a default `getSchedulerStatus` mock added to its two existing `describe` blocks' `beforeEach` (since `AutoSyncStatusSection` now mounts on every render of the Connections page — the pre-existing 17 EP-22/EP-23.3 tests needed no assertion changes, only the added mock so they don't hit real `fetch`). `Settings.test.tsx` gained a new `describe` block (4 tests: disabled state hides the interval picker, enabled state shows interval/next-sync/health, toggling the switch calls `updateSchedulerSettings` with `{auto_sync_enabled: true}`, changing the select calls it with `{interval: "6h"}`) plus a default `getSchedulerStatus` mock in the pre-existing suite's `beforeEach`. Full dashboard suite: **191 passed** (184 + 7), lint clean, typecheck clean (`tsc -b`), build clean.

### Known limitations

- **Lock TTL, not lease renewal.** The Redis lock's TTL is set once at acquisition (`clamp(interval_seconds, 60, 86400)`) and never extended while a job runs. A sync that takes longer than the org's own configured interval (unusual, but possible for a very short 5-minute interval against a slow provider) could have its lock expire before the job finishes, allowing the *next* tick to dispatch a second, overlapping job for the same org — the in-process guard (`_running_org_ids`) still prevents this within one worker, so this is only a real risk across multiple horizontally-scaled workers with a short interval and an unusually slow provider. A lease-renewal heartbeat would close this gap; not built here to keep the locking mechanism the "smallest possible, production-quality change" the task asked for.
- **`SchedulerJobRecord` history is in-memory and per-process.** Restarting the API process (or running multiple workers) means `GET .../scheduler/jobs` and the monitoring counters only reflect *that process's* recent activity, not a global history — by design (see the architecture section's rationale), but worth restating: the durable record of what actually synced is always `UsageCollectionRun`, never this job history.
- **No startup-storm smoothing.** On a fresh deploy (or after `scheduler_enabled` is flipped on for the first time), every organization with auto-sync on and no prior `SCHEDULED` run is immediately "due," so the first tick can dispatch many organizations at once — bounded by `max_concurrent_orgs` (default 5) so they queue rather than all running simultaneously, but there is no jitter/stagger added across organizations' *first* sync. Acceptable at this product's current scale; would be the first thing to revisit if the organization count grows large enough for a synchronized first-tick burst to matter.
- **`retry_count` is scheduler-job-level, not HTTP-request-level** (see "Retry flow" above) — disclosed there, repeated here because it's the one field in this EP most likely to be misread as "how many times did the HTTP client retry."
- **No live, continuous browser test of a real multi-tick scheduler run** — same caveat as every prior EP in this document: verified in pieces (backend unit tests calling `tick()`/`_run_job()` directly rather than running the real sleep loop, frontend component tests, both full builds), not as one continuous browser session watching real background ticks fire over real wall-clock time, since this sandbox has no way to drive a real browser against a live deployment or wait out real intervals.

### Next EP recommendation

With both manual (EP-23.3) and automatic (EP-23.4) usage synchronization now real, the two items §19 already named as the standing next blockers are unaffected by this EP and remain the highest-value work: (1) **dashboard analytics on top of the newly-flowing data** — now doubly unblocked, since `UsageEvent`/`UsageCostRecord` rows can arrive without any user action at all; and (2) the lease-renewal/startup-jitter hardening named above, if and when this product's organization count or per-org sync frequency grows enough to make either a real concern rather than a theoretical one.
