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

The product today is **two separate frontends** that need to become one seamless experience:
- A **marketing website** (public, unauthenticated) — currently a separate repo (`costorah-ai-guide-main`, Lovable-built).
- An **authenticated dashboard application** (this repo's `frontend/`) — the product itself.

They share a backend (`backend/`, FastAPI) but nothing else yet: different frameworks, different design token systems, different auth models, different repos.

---

## 2. Repository Structure

### Current
```
AI-FinOps/                  (pnpm workspace: frontend + packages/*)
├── frontend/                @ai-finops/frontend — Vite SPA dashboard
├── backend/                 FastAPI monolith
├── packages/
│   ├── shared-types/        @ai-finops/shared-types
│   ├── shared-config/       @ai-finops/shared-config
│   ├── api-contracts/       @ai-finops/api-contracts
│   ├── event-schema/        @ai-finops/event-schema
│   ├── error-codes/         @ai-finops/error-codes
│   └── ui-components/       empty stub — seed for shared-ui
├── sdk/                      @costorah/sdk (Python + JS) — external-facing, different npm scope than the rest
├── provider-adapters/, monitoring-agent/, docs/, deployment/, ...
```

### Target (see `costorah_website_dashboard_merge_plan.md` for the full migration plan)
```
AI-FinOps/
├── apps/
│   ├── website/              ← migrated from costorah-ai-guide-main via git subtree (history preserved)
│   └── dashboard/             ← renamed from frontend/
├── backend/                   unchanged location
├── packages/
│   ├── shared-ui/              ← fills the ui-components stub; shadcn/ui-based, shared by both apps
│   ├── shared-types/, shared-config/, api-contracts/, event-schema/, error-codes/  ← existing, extended
│   └── shared-utils/           ← new: cn(), formatting, PROVIDER_COLORS
├── sdk/, provider-adapters/, monitoring-agent/, docs/, deployment/
```

**Package naming**: all internal workspace packages move to the `@costorah/*` scope (matching the already-public `@costorah/sdk`), retiring the `@ai-finops/*` scope in the same PR that does the directory restructure (EP-25).

---

## 3. Website Architecture

Source (pre-migration): `costorah-ai-guide-main`, uploaded as a Lovable export.

- **Framework**: TanStack Start — SSR, file-based routing (`src/routes/*.tsx`), root shell `__root.tsx`. Not a static site; requires a running SSR server (Nitro, Cloudflare-targeted by its build config).
- **Styling**: Tailwind v4, CSS-first config (no `tailwind.config.*` — tokens live in `src/styles.css` via `@theme inline`). OKLCH color space, dark-only palette (no light mode built). Brand color `#14D9D3` → `#7AF7E8` (teal → mint).
- **Components**: shadcn/ui (Radix-based) fully installed (38 primitives in `src/components/ui/`) but **currently unused** — pages use raw Tailwind instead. Custom shell components: `SiteLayout`, `SiteNav`, `SiteFooter`, `PageHeader`, `StubPage`, inline-SVG `LogoMark`.
- **Fonts**: Inter (body), Space Grotesk (display), JetBrains Mono (code) — all via Google Fonts `<link>` tags. Same families as the dashboard, different loading mechanism (link tags vs. CSS `@import`).
- **Routes**: 13 total. Only 4 have real content — `/` (landing page), `/contact`, `/login`, `/signup`. The other 9 (`about`, `blog`, `developers`, `docs`, `features`, `pricing`, `security`, `privacy`, `terms`) are `StubPage` placeholders with no unique copy.
- **Backend integration**: none. `/login`, `/signup`, `/contact` are static forms — `onSubmit` only calls `preventDefault()`. No fetch calls, no auth library, despite `react-hook-form`/`zod` being installed.
- **Deployment**: no committed config (no Dockerfile/vercel.json/wrangler.toml); currently built and hosted entirely by Lovable's pipeline. Nitro's build defaults to a Cloudflare target.

## 4. Dashboard Architecture

Source: `frontend/` (target: `apps/dashboard/`).

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

### Current
- **Browser session (dashboard)**: bearer JWT. Access token held in memory only (Zustand, not persisted — explicit XSS mitigation). Refresh token persisted to `localStorage` only if "remember me" was checked. `ProtectedRoute` silently calls `POST /v1/auth/refresh` on mount if only a refresh token survives a reload. No cookies involved anywhere.
- **Website**: no auth wiring at all — `/login`/`/signup` are static mockups.
- **M2M / SDK**: separate mechanism, Organization API Keys (`Authorization: Bearer costorah_live_...`), validated by `CurrentApiKey`/`RequireApiKeyPermission`. This layer is correct as-is and is **not** part of the browser-session change below — API keys and browser sessions are and should remain distinct concerns.

### Target
Move **browser session** auth (not the API-key path) to an **httpOnly, `SameSite=Lax` cookie scoped to the shared parent domain** (`.costorah.com`). This is what makes cross-app navigation actually seamless (matching GitHub/Linear/Vercel/Supabase) without token-in-URL handoff tricks:

1. Backend issues the session cookie on `POST /v1/auth/login` and the (currently missing) `POST /v1/auth/register`.
2. `apps/website`'s `/login`/`/signup` call these endpoints directly; on success, redirect to the dashboard subdomain — the cookie is already valid there because it's the same parent domain.
3. `apps/dashboard`'s API client switches from attaching `Authorization: Bearer <token from Zustand>` to `credentials: "include"`.
4. Logout clears the cookie server-side; both apps redirect to the website root.

### Domain topology
`costorah.com` → website (SSR, Cloudflare). `app.costorah.com` → dashboard (static SPA build, same host as today — currently Render). Subdomain, not path-prefix, because the SSR/SPA split makes a shared reverse-proxy path-routing setup extra infrastructure for no benefit, and a shared parent domain is exactly what the cookie model above needs.

---

## 7. Workspace / Organization Architecture

**"Workspace" in the requested product flow = the existing `Organization` entity.** No second data model is introduced — this matches how Linear/Vercel/Notion model personal and team workspaces as the same underlying entity.

- **Personal workspace auto-creation**: on registration, the backend creates one `Organization` row (named after the user, e.g. "Jane's Workspace") with the new user as sole `Owner`. Requires an org-creation code path — today there is **no organization-create endpoint at all** (only `GET /v1/organizations` — list mine).
- **Switching workspaces**: already implemented — `OrgSelector.tsx` + `useOrgStore` handle multi-org membership. This part is in reasonable shape; it just currently has nothing to switch *to* beyond a hand-seeded org, since general-purpose org creation doesn't exist yet.
- **Inviting members**: real and working (`POST /v1/organizations/{id}/members`) — but invite emails are never delivered, because **no outbound email transport exists anywhere in the platform**. The same gap silently breaks password-reset and verification emails. One transactional-email integration fixes all three.
- **Projects**: modeled (`Project` entity, repository) but **no CRUD API exists** — only used internally by usage ingestion to validate `project_id`.
- **Provider Connections**: modeled (`ProviderConnection` entity, repository) but **never wired to any router** — the only provider-related endpoints today (`/v1/providers/{provider}/test|models|info`) are a stateless connectivity probe against server-side environment-variable keys, not a customer-entered, persisted credential. This is the concrete blocker for the "Connect OpenAI / Connect Anthropic" onboarding steps being real rather than a demo.

---

## 8. Migration Roadmap

Dependency-ordered. Extends the EP-21+ roadmap from the prior product-completeness audit.

1. **EP-21 — Registration + personal workspace auto-provisioning.** `POST /v1/auth/register` + org auto-creation on signup. Nothing downstream matters until a new customer can get in.
2. **EP-22 — Cookie-based session + domain topology.** Session-cookie issuance scoped to `.costorah.com`; establishes `costorah.com` / `app.costorah.com`.
3. **EP-23 — Provider Connections (real, persisted).** Full CRUD API + UI for the already-modeled `ProviderConnection` entity.
4. **EP-24 — Projects CRUD.** Same treatment for `Project`.
5. **EP-25 — Monorepo restructure.** `frontend/` → `apps/dashboard`; website merged into `apps/website` via `git subtree` (history preserved, not a flat copy); `packages/ui-components` → `packages/shared-ui`; package scope unified to `@costorah/*`; Turborepo introduced.
6. **EP-26 — Design system unification.** Token reconciliation per the table in §5; dashboard migrated onto shared shadcn/ui primitives; fonts self-hosted; `PROVIDER_COLORS` centralized.
7. **EP-27 — Onboarding wizard completion.** Wire `OnboardingModal` through the real Connect-Provider (EP-23) flow and usage-ingestion activation.
8. **EP-28 — Transactional email.** One implementation; fixes verification, password reset, and member invites at once.
9. **EP-29 — Website content completion.** Real copy for the 9 existing stub pages, plus net-new pages your spec calls for that don't exist in the source repo at all: **Enterprise, Integrations, Roadmap, Careers, Status**.
10. **EP-30 — Unified CI/CD.** Extend GitHub Actions to build/test/typecheck both apps + shared packages via Turborepo; separate deploy jobs (Cloudflare SSR for website, static hosting for dashboard) from one pipeline.
11. **EP-31 — Billing.** Still fully absent (no Stripe/subscription code anywhere per the prior audit) — correctly last, since there's no self-serve product to charge for until EP-21–24 land.

Full rationale, the component/token reconciliation tables, and the "what this plan deliberately does not recommend" section live in `costorah_website_dashboard_merge_plan.md` (delivered alongside this document).
