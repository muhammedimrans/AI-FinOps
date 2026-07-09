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

---

## 3. Website Architecture

Location: `apps/website/` (imported from the standalone `costorah-ai-guide-main` Lovable export — see §2 and §8 milestone 2).

- **Framework**: TanStack Start — SSR, file-based routing (`src/routes/*.tsx`), root shell `__root.tsx`. Not a static site; requires a running SSR server (Nitro, Cloudflare-targeted by its build config).
- **Styling**: Tailwind v4, CSS-first config (no `tailwind.config.*` — tokens live in `src/styles.css` via `@theme inline`). OKLCH color space, dark-only palette (no light mode built). Brand color `#14D9D3` → `#7AF7E8` (teal → mint).
- **Components**: shadcn/ui (Radix-based) fully installed (38 primitives in `src/components/ui/`) but **currently unused** — pages use raw Tailwind instead. Custom shell components: `SiteLayout`, `SiteNav`, `SiteFooter`, `PageHeader`, `StubPage`, inline-SVG `LogoMark`.
- **Fonts**: Inter (body), Space Grotesk (display), JetBrains Mono (code) — all via Google Fonts `<link>` tags. Same families as the dashboard, different loading mechanism (link tags vs. CSS `@import`).
- **Routes**: 13 total. Only 4 have real content — `/` (landing page), `/contact`, `/login`, `/signup`. The other 9 (`about`, `blog`, `developers`, `docs`, `features`, `pricing`, `security`, `privacy`, `terms`) are `StubPage` placeholders with no unique copy.
- **Backend integration**: none. `/login`, `/signup`, `/contact` are static forms — `onSubmit` only calls `preventDefault()`. No fetch calls, no auth library, despite `react-hook-form`/`zod` being installed.
- **Deployment**: no committed config (no Dockerfile/vercel.json/wrangler.toml); currently built and hosted entirely by Lovable's pipeline. Nitro's build defaults to a Cloudflare target.

## 4. Dashboard Architecture

Location: `apps/dashboard/` (moved from this repo's former `frontend/` — see §2 and §8 milestone 1).

- **Framework**: Vite SPA, React 18.3, React Router v6 (`BrowserRouter`, classic `<Routes>`), served at root `/` with no base path.
- **Styling**: Tailwind v3.4 (TS config file). No shadcn/ui or Radix — every primitive (`Dialog`, `Popover`, `Avatar`, `ConfirmDialog`, `MetricCard`, `ToastContainer`) is hand-rolled, using Framer Motion for animation.
- **Theming**: a **3-theme system** — `neon-cyber` (default), `professional-light`, `professional-dark` — switched via `data-theme` attribute on `<html>`, controlled by `useThemeStore` (Zustand, manual `localStorage` write, not the `persist` middleware). An inline blocking `<script>` in `index.html` sets the initial theme pre-render to avoid FOUC. RGB-triplet CSS custom properties, consumed as `rgb(var(--x) / alpha)`.
- **Fonts**: Inter + Space Grotesk via CSS `@import` in `index.css`. JetBrains Mono is declared in the Tailwind config but **never actually loaded** — a latent bug to fix during font unification.
- **State**: Zustand, 8 stores (`auth`, `org`, `theme`, `ui`, `notifications`, `onboarding`, `profile`, `toast`).
- **Data fetching**: TanStack Query v5.
- **Routes** (all lazy-loaded, each wrapped in its own `ErrorBoundary`): 19 `src/features/*.tsx` files. Public: `/login`, `/forgot-password`, `/reset-password`, `/verify-email`. Protected (behind `ProtectedRoute` + an org-membership `AuthGuard`): `/dashboard` (+ `/analytics`, `/providers`, `/models`, `/projects`, `/organization`, `/pricing`), `/users`, `/rbac`, `/api-keys`, `/connections`, `/audit-logs` (placeholder), `/settings`, `/support`.
- **Known gaps carried into this migration** (from the prior product-completeness audit): no self-serve registration exists in this app; `Settings.tsx` doesn't persist anything to the backend despite a full save UI; `/audit-logs` is a nav-reachable placeholder.

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
- **M2M / SDK**: unchanged — separate mechanism, Organization API Keys (`Authorization: Bearer costorah_live_...`), validated by `CurrentApiKey`/`RequireApiKeyPermission`. Not part of the browser-session cookie work; API keys and browser sessions remain distinct concerns.

### Remaining for full seamless handoff
1. `apps/dashboard`'s API client migrates from `Authorization: Bearer <token from Zustand>` to `credentials: "include"`, letting the cookie carry the session instead of JS-managed tokens. Not required today — the fragment handoff already gets a fresh registrant from the website into a working dashboard session — but is the natural cleanup that lets `consumeSessionHandoff.ts` and `buildDashboardHandoffUrl()` be deleted, and lets `apps/dashboard`'s own `Login.tsx` be retired in favor of the website's `/login`.

### Domain topology
`costorah.com` → website (SSR, Cloudflare). `app.costorah.com` → dashboard (static SPA build, same host as today — currently Render). Subdomain, not path-prefix, because the SSR/SPA split makes a shared reverse-proxy path-routing setup extra infrastructure for no benefit, and a shared parent domain is exactly what the cookie model above needs.

---

## 7. Workspace / Organization Architecture

**"Workspace" in the requested product flow = the existing `Organization` entity.** No second data model is introduced — this matches how Linear/Vercel/Notion model personal and team workspaces as the same underlying entity.

- **Personal workspace auto-creation**: ✅ done (EP-21.2). `POST /v1/auth/register` creates one `Organization` row (`is_personal=True`, named `"{display_name}'s Workspace"`, unique slug) with the new user as sole `OWNER` `Membership`, in the same transaction as the `User` row — `AuthService.register()`. There is still no *general-purpose* org-create endpoint (only this registration-time special case, plus the pre-existing `GET /v1/organizations` — list mine) — creating a second, non-personal team org is not yet possible via the API.
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
2. **EP-22 — Provider Connections (real, persisted).** Full CRUD API + UI for the already-modeled `ProviderConnection` entity. Not started.
3. **EP-23 — Projects CRUD.** Same treatment for `Project`. Not started.
4. **EP-24 — Onboarding wizard completion.** Wire `OnboardingModal` through the real Connect-Provider (EP-22) flow and usage-ingestion activation. Not started.
5. **EP-25 — Transactional email.** One implementation; fixes verification, password reset, and member invites at once. Not started.
6. **EP-26 — Website content completion.** Real copy for the 9 existing stub pages, plus net-new pages the product spec calls for that don't exist in the source repo at all: **Enterprise, Integrations, Roadmap, Careers, Status**. Not started.
7. **EP-27 — Billing.** Still fully absent (no Stripe/subscription code anywhere per the prior audit) — correctly last, since there's no self-serve product to charge for until EP-21–24 land. Not started.

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
