# Costorah — Website + Dashboard Unification: Migration Strategy

Read-only planning document. No code was written or restructured as part of this task — this is the plan, per your instruction not to simply copy files. `CLAUDE.md` was created at the repo root as the permanent architecture record (Part 8 below mirrors its content).

---

## Part 0 — What Exists Today (ground truth from direct inspection)

### Repository A — `AI-FinOps` (this repo)
- **Already a pnpm workspace** (`pnpm-workspace.yaml`: `frontend`, `packages/*`), version `0.1.0`, package manager pinned `pnpm@9.0.0`.
- `packages/` already contains real, in-use scaffolding: `shared-types`, `shared-config`, `api-contracts`, `event-schema`, `error-codes` (all `@ai-finops/*` scope, built with `tsc`), plus an **empty stub** `ui-components` (README only, no code — this is the natural seed for the shared design-system package).
- `frontend/` (`@ai-finops/frontend`): Vite SPA, React 18.3, **React Router v6**, **Tailwind v3.4** (JS/TS config), zero shadcn/ui or Radix — every primitive (`Dialog`, `Popover`, `Avatar`, `MetricCard`, etc.) is hand-rolled with Framer Motion. Theming is a **3-theme system** (`neon-cyber`, `professional-light`, `professional-dark`) driven by `data-theme` on `<html>`, backed by RGB-triplet CSS vars, not Tailwind's `dark:` class strategy. Fonts: Inter + Space Grotesk loaded via `@import` in CSS; **JetBrains Mono is configured but never actually loaded** (latent bug). Auth is **bearer-token, no cookies** — access token memory-only, refresh token in `localStorage` only if "remember me" is checked. **No self-serve registration exists in this app.**
- `backend/`: FastAPI, fully audited in the prior product-completeness report. Relevant gaps that this migration directly depends on: **no registration endpoint, no organization-create endpoint, no project-create endpoint, no persisted provider-connection entity.** These are hard blockers for the Registration/Organization flows this task specifies — see Part 6.
- `sdk/javascript` already publishes under a **different** npm scope: `@costorah/sdk`. This is an existing naming inconsistency (`@ai-finops/*` internal packages vs. `@costorah/*` public SDK) that predates this task — worth resolving in the same pass as the merge, not compounding it with a third scope.

### Repository B — `costorah-ai-guide-main` (the uploaded Lovable site)
- **TanStack Start** (SSR React framework, file-based routing in `src/routes/`), not a plain Vite SPA. Built via a Lovable-managed wrapper (`@lovable.dev/vite-tanstack-config`) that defaults its Nitro build target to **Cloudflare**. Package manager is **Bun**. React **19.2**.
- **Tailwind v4**, CSS-first config (no `tailwind.config.*` file — tokens live entirely in `src/styles.css` via `@theme inline`). **shadcn/ui is fully installed** (38 Radix-based primitives in `src/components/ui/`) but **currently unused** by any actual page — the landing page and stub pages use raw Tailwind classes instead.
- Design tokens: **OKLCH color space**, dark-only (no light mode implemented), brand hex `#14D9D3` / `#7AF7E8` (teal → mint gradient) used both as CSS vars and repeated as raw arbitrary Tailwind values (`bg-[#0C1117]`, `text-[#14D9D3]`) — token discipline is looser than the dashboard's.
- Fonts: **same two primary families as the dashboard** — Inter (body) and Space Grotesk (display) — plus JetBrains Mono, all three actually loaded via Google Fonts `<link>` tags (unlike the dashboard, which never loads Mono). This overlap is good news: font unification is nearly free.
- **13 routes total, only 4 have real content**: `/` (full landing page), `/contact`, `/login`, `/signup`. The other 9 (`about`, `blog`, `developers`, `docs`, `features`, `pricing`, `security`, `privacy`, `terms`) render a generic `StubPage` placeholder with no unique copy.
- **Zero backend integration anywhere.** `/login`, `/signup`, `/contact` all call `e.preventDefault()` and nothing else — no fetch, no auth library, no validation wiring despite `react-hook-form`/`zod` being installed. This is pure UI mockup.
- No deployment config committed (no `Dockerfile`/`vercel.json`/`wrangler.toml`/CI workflow) — deployment today is entirely Lovable's managed pipeline.
- Package name is still the generic Lovable template default (`"tanstack_start_ts"`), never renamed.

### The core architectural tension
The website is **SSR** (TanStack Start/Nitro, needed for marketing SEO) and the dashboard is a **client-only SPA** (Vite/React Router, appropriate for an authenticated app). These are two different rendering models and two different routers. **Forcing them into one framework is not the right move** — none of the reference products you named (GitHub, Vercel, Supabase, Clerk, Railway, Neon, Linear) run their marketing site and app on the same router/framework instance either; they achieve the "seamless" feel through **shared design system + shared domain + a real session handoff**, not a shared codebase-level router. The plan below follows that same pattern.

---

## Part 1 — Target Repository Structure

Building on the pnpm workspace that already exists, not replacing it:

```
AI-FinOps/
├── apps/
│   ├── website/            ← migrated from costorah-ai-guide-main (TanStack Start, SSR)
│   └── dashboard/          ← renamed from frontend/ (Vite SPA, React Router)
├── backend/                ← unchanged location, FastAPI
├── packages/
│   ├── shared-ui/          ← fills the existing empty ui-components stub; shadcn/ui-based
│   ├── shared-types/       ← existing, extended
│   ├── shared-config/      ← existing
│   ├── api-contracts/      ← existing
│   ├── event-schema/       ← existing
│   ├── error-codes/        ← existing
│   └── shared-utils/       ← new: cn(), date/currency formatting, provider brand constants
├── sdk/                    ← unchanged (Python + JS SDKs, external-facing)
├── provider-adapters/      ← unchanged
├── monitoring-agent/       ← unchanged
└── docs/, deployment/, etc. ← unchanged
```

`ui-components` gets renamed to `shared-ui` for clarity against the `apps/` naming, or kept as-is and just filled in — either is fine; `shared-ui` is recommended since it matches the naming pattern the task description used.

**Package naming**: standardize every internal workspace package on `@costorah/*` (matching the already-public `@costorah/sdk`) and rename the five existing `@ai-finops/*` packages in the same PR that does the directory move — doing it in one pass avoids a second churn cycle across every import site.

**Turborepo**: with two apps and 6+ shared packages, plain `pnpm --recursive` (today's approach) will start doing redundant rebuilds. Recommend introducing Turborepo (`turbo.json`) in the same restructuring PR — it's additive on top of the existing pnpm workspace, not a replacement.

---

## Part 2 — What Gets Reused, Deleted, or Changed

### Components: reuse as-is
- `SiteLayout`, `SiteNav`, `SiteFooter`, `PageHeader`, `StubPage`, and the inline SVG `LogoMark` from the website — these are website-specific shell components with no dashboard equivalent; they move into `apps/website/src/components/site/` unchanged.
- The dashboard's domain-specific components (`MetricCard`, `BudgetBar`, `AlertTimeline`, `LiveActivityFeed`, `ProviderBadge`, `ConnectionIndicator`, chart wrappers) stay in `apps/dashboard` — they're app-specific, not shared.

### Components: consolidate into `packages/shared-ui`
- The website's 38-file shadcn/ui set (`button`, `card`, `dialog`, `input`, `select`, `tabs`, `dropdown-menu`, `avatar`, `badge`, `tooltip`, `popover`, `separator`, `sheet`, `table`, `toggle`, `switch`, etc.) is currently installed but **unused** on the website side, and the dashboard has **hand-rolled equivalents** for a subset of the same concepts (`Dialog.tsx`, `Popover.tsx`, `Avatar.tsx`, `ConfirmDialog.tsx`, `ToastContainer.tsx`).
- **Recommendation: adopt shadcn/ui as the one shared primitive layer**, seeded in `packages/shared-ui`, and retire the dashboard's hand-rolled equivalents in favor of it. Rationale: the website already has the full set installed and correctly wired to Tailwind v4 + Radix; the dashboard's hand-rolled versions would otherwise need to be extracted, generalized, and maintained a second time. This is real migration work (each dashboard screen that imports `Dialog`/`Popover`/`Avatar` needs a follow-up pass), not a zero-cost rename — sized explicitly in the roadmap (Part 7, EP-26).
- Components that exist on **both** sides conceptually — toast/notification rendering (dashboard's `ToastContainer` + `stores/toast.ts` vs. website's unused shadcn `sonner`) — consolidate onto **one** implementation. Recommend `sonner` (already a website dependency, shadcn-standard) as the shared toast system, with the dashboard's `toast.ts` store adapted to call it instead of maintaining a bespoke renderer.

### Components: delete
- `src/lib/error-capture.ts`, `error-page.ts`, `lovable-error-reporting.ts` and the `.lovable/` directory in the website repo — these are Lovable-platform-specific plumbing (`window.__lovableEvents`) with no purpose once the site leaves Lovable's managed pipeline. Replace with the dashboard's existing `ErrorBoundary.tsx` pattern or a shared one in `packages/shared-ui`.
- The website's `src/hooks/use-mobile.tsx` is unused by any current route — either delete or fold into `packages/shared-utils` if a mobile-breakpoint hook is genuinely needed by both apps (the dashboard doesn't currently have one either; don't invent a need).

### Pages: overlap and routing changes
- `login.tsx` / `signup.tsx` (website, currently static mockups) and the dashboard's real `Login.tsx` (React Router, wired to `POST /v1/auth/login`) are the same conceptual page implemented twice, once fake and once real. **Do not keep both as separate implementations.** Recommend: the website's `/login` and `/signup` routes become the **only** entry points for authentication (matching the requested flow: Visitor → Website → Register/Login), calling the real backend directly from `apps/website` (TanStack Start supports server functions / API routes, or it can call the FastAPI backend directly from the client like the dashboard does). The dashboard's `Login.tsx`, `ForgotPassword.tsx`, `ResetPassword.tsx`, `VerifyEmail.tsx` routes and files are then **deleted** — an already-authenticated user should never see them; an unauthenticated user hitting a dashboard URL directly gets redirected to the website's `/login`, not shown a second login page.
- `contact.tsx` (website, currently a no-op form) needs a real backend target. The product audit found no contact/support-ticket backend exists (the dashboard's own `Support.tsx` page has the identical gap, explicitly labeled "coming soon"). This is one gap, not two — build one contact-submission backend endpoint and point both the website contact form and (if kept) the dashboard support form at it, or retire the dashboard's redundant Support page in favor of the website's Contact page.

### Design tokens: what becomes shared vs. app-specific
| Token category | Decision |
|---|---|
| Font families (Inter, Space Grotesk, JetBrains Mono) | **Share.** Already the same families on both sides — this is the easiest win. Move to `packages/shared-ui/tokens/fonts.css`, self-host the font files (both apps currently depend on a live Google Fonts request; self-hosting removes an external runtime dependency and fixes the dashboard's never-loaded JetBrains Mono in the same change). |
| Brand color (teal/mint) | **Share the hue, reconcile the exact values.** Website: `#14D9D3`/`#7AF7E8` (OKLCH-authored). Dashboard: a similarly-teal `--color-brand` (RGB-triplet-authored) plus a legacy indigo `--color-primary`. Pick one canonical brand teal value and one color-space convention (recommend OKLCH, since Tailwind v4 — the direction the website already uses — treats it as first-class, and both `apps` can consume the same CSS custom properties regardless of which Tailwind major version each app runs). |
| Dark/light theming model | **This is the one real conflict.** Website is dark-only (no light mode built). Dashboard has a 3-theme system (`neon-cyber`, `professional-light`, `professional-dark`) via `data-theme`. Recommend: standardize on the dashboard's `data-theme` attribute mechanism (it's the more complete system) and treat the website's current dark palette as the seed for a shared `neon-cyber` token set; add `professional-light`/`professional-dark` to the website only if/when it needs a theme switcher (it may not — marketing sites are commonly single-theme by design; don't force one on it if it's not wanted). |
| Radius/shadow/spacing scale | **Reconcile, then share.** Website: base radius 14px, OKLCH shadow tokens. Dashboard: `card` 12px/`card-lg` 20px/`card-xl` 28px, RGB-alpha shadow tokens. Pick one scale (recommend the dashboard's, since it's already exercised across 19 real screens vs. the website's 4) and apply it to the website during content migration. |
| Provider brand colors (OpenAI green, Anthropic tan, etc.) | **Share as-is** — dashboard already has these as hardcoded hex constants; website doesn't have them yet (its landing page doesn't badge individual providers with brand colors). Move to `packages/shared-utils` as a single source of truth (`PROVIDER_COLORS`), consumed by both the dashboard's `ProviderBadge` and any future website provider-logo display. |

---

## Part 3 — Authentication & Session Handoff

This is the part that makes the transition feel "seamless" like the reference products, and it's currently the biggest structural gap: **the dashboard's session is bearer-token-in-JS-memory/localStorage, not a cookie** — nothing shares automatically across origins or even across a page reload without the refresh dance already implemented in `ProtectedRoute.tsx`.

**Recommended target model** (matches how GitHub/Linear/Vercel/Supabase actually do it): move to an **httpOnly, `SameSite=Lax` session cookie scoped to the parent domain** (`.costorah.com`), issued by the backend on login/register, readable by both `costorah.com` (website) and wherever the dashboard is served (see Part 4 for the domain decision). The existing bearer-token flow doesn't have to be thrown away — it's still exactly right for the **API-key** and **SDK/M2M** paths (`Authorization: Bearer costorah_live_...`), which are a separate concern from **browser session** auth. Only the browser-facing login/session layer changes.

Concretely:
1. Backend: `POST /v1/auth/login` and the (currently missing) `POST /v1/auth/register` set an httpOnly cookie in addition to (or instead of) returning tokens in the JSON body. Refresh becomes cookie-driven too — no more manual refresh-token juggling in `localStorage`.
2. `apps/website`'s `/login` and `/signup` pages call these endpoints directly, and on success redirect the browser to the dashboard's URL — the cookie is already present, so the dashboard's own `ProtectedRoute` check succeeds immediately with zero extra handoff code (no token-in-URL, no postMessage, no OAuth-style code exchange needed, because it's the same top-level domain).
3. `apps/dashboard`'s `services/api.ts` changes from attaching `Authorization: Bearer` from a Zustand store to relying on the cookie (`credentials: "include"`), matching the backend change.
4. Logout clears the cookie server-side and both apps redirect to the website's root.

This is real backend + frontend work (not a config toggle) and should be its own EP rather than a side effect of the directory move — see Part 7, EP-22.

---

## Part 4 — Domain / Deployment Topology

Two viable patterns, both used by the reference products you cited:

- **Subdomain split** (Linear: `linear.app` marketing, `linear.app/... ` app is actually same app; GitHub: `github.com` both; Supabase: `supabase.com` marketing, `app.supabase.com` dashboard; Vercel: `vercel.com` marketing, `vercel.com/dashboard` app under same domain but Next.js unifies routing). Precedent supports **either** a subdomain (`app.costorah.com`) or a path prefix (`costorah.com/app`) on the same root domain.
- Given the SSR-vs-SPA framework split identified above, **subdomain is the pragmatic choice here**: `costorah.com` → `apps/website` (TanStack Start/Nitro, SSR, deployed to Cloudflare per its existing build target), `app.costorah.com` → `apps/dashboard` (Vite SPA static build, deployed as a static bundle same as today, currently on Render per `.env.production`). A shared parent domain (`.costorah.com`) is what makes the Part 3 cookie-sharing model work without any cross-origin gymnastics.
- Path-prefix (`costorah.com/app/*`) is possible but would require a reverse proxy in front of both deployments (routing SSR vs. static-SPA traffic by path) — more infrastructure for no real benefit over the subdomain approach, given neither app needs to share URL space with the other.

---

## Part 5 — Registration & Workspace Flow (mapping your spec onto what exists)

Your requested flow:
```
Visitor → Marketing Website → Get Started → Register → Email Verification →
Personal Workspace auto-created → Onboarding Wizard →
Connect OpenAI → Connect Anthropic → Import Usage → Dashboard
```

Mapped against current backend reality (from the prior product audit):

| Step | Exists today? | What's needed |
|---|---|---|
| Register | **No.** No `/v1/auth/register` endpoint; website's `/signup` is a static mockup. | New backend endpoint + wire website form to it. |
| Email Verification | **Partially.** `POST /v1/auth/verify-email` exists and is real; the dashboard has a working `VerifyEmail.tsx` (moves to website, per Part 2). | Just needs a registration flow to trigger it — no outbound email transport exists platform-wide yet (flagged in the prior audit), so verification emails don't currently get delivered even though the token endpoint works. |
| Personal Workspace auto-created | **No.** No organization-create endpoint at all; "workspace" isn't a distinct backend concept — the existing `Organization` model is the right substrate for it. | Recommend: **Workspace = Organization** in the data model (don't introduce a second entity). Registration creates one `Organization` row named after the user (e.g. "Jane's Workspace") with the new user as sole `Owner`, exactly the personal-workspace pattern Linear/Vercel/Notion use. Requires the missing org-create capability, scoped specifically to this auto-provisioning path (not necessarily a general-purpose "create org" UI on day one). |
| Onboarding Wizard | **Partially.** `OnboardingModal.tsx` already exists in the dashboard's component tree (per the design-system inventory) — worth checking whether it's already wired to anything or is itself a shell; either way it's the right place to build this. | Extend/build out to cover the next two steps. |
| Connect OpenAI / Connect Anthropic | **No persisted version exists.** `ProviderConnection` model + repository are fully coded but never wired to any API router (confirmed in the prior audit) — today's `Connections.tsx` page only does a **stateless** test against server-side environment-variable keys, not a customer-entered, stored credential. | This is a real backend feature gap, not just UI — needs the `ProviderConnection` CRUD API built (flagged as EP-22 in the prior product audit; renumbered EP-23 here to slot after the auth/workspace work, see Part 7). |
| Import Usage | **Ambiguous with existing gaps.** The real ingestion path (`POST /v1/ingest/usage`) is SDK-driven, not a UI button; the UI's own "Collect Usage" action (`/usage/collect`) exists but explicitly never persists its results (a stub, per the prior audit). | Decide product intent: is "Import Usage" a one-time historical backfill (pull past usage from the provider's own billing API) or is it just "you've now connected a provider, usage will start flowing via the SDK/ingestion pipeline going forward"? These are different features. Recommend the latter for MVP (it's what the backend already has a real path for) and rename the wizard step accordingly rather than building a new historical-import feature speculatively. |
| Dashboard | **Works**, once the above are in place. | — |

## Part 6 — Organization Flow (post-login)

```
Create Organization → Invite Members → Switch Workspace → Create Projects → Share Providers
```

- **Create Organization** (beyond the auto-created personal one): still missing — same gap as Part 5, but now needed as a general-purpose, user-facing action, not just the registration-time special case.
- **Invite Members**: already real (`POST /v1/organizations/{id}/members`), works today — but invite emails are never delivered (no outbound email transport, same root cause as the verification-email gap above). One transactional-email project fixes three separate flows (verify, reset, invite) — don't solve it three times.
- **Switch Workspace**: `OrgSelector.tsx` + `useOrgStore` already implement workspace switching for users with multiple orgs — this one's in reasonable shape already, mostly needs the "create another org" gap filled so there's ever a second workspace to switch to.
- **Create Projects**: missing (no `Project` CRUD API, per prior audit) — same shape of gap as organizations.
- **Share Providers**: implies a provider connection can be scoped to an organization and made visible to multiple projects/members within it — this falls out naturally once the `ProviderConnection` API (Part 5) exists with organization-level scoping, doesn't need to be a separate feature.

---

## Part 7 — Migration Roadmap (dependency-ordered, highest business value → lowest)

This extends (doesn't replace) the EP roadmap from the prior product-completeness audit — EP-21 there was "self-service onboarding," which this plan makes concrete.

1. **EP-21 — Registration + personal workspace auto-provisioning.** Backend: `POST /v1/auth/register`, org auto-creation on signup. This unblocks literally everything downstream — the current product has no way for a new customer to get in at all.
2. **EP-22 — Cookie-based session + domain topology.** Backend session-cookie issuance scoped to `.costorah.com`; establishes the subdomain split (`costorah.com` / `app.costorah.com`) this whole plan depends on for a seamless handoff.
3. **EP-23 — Provider Connections (real, persisted).** Wires the already-modeled `ProviderConnection` entity to a full CRUD API + UI — required for the "Connect OpenAI / Connect Anthropic" onboarding steps to be real rather than a server-env-var demo.
4. **EP-24 — Projects CRUD.** Same treatment for the already-modeled `Project` entity.
5. **EP-25 — Monorepo restructure.** The directory move itself: `frontend/` → `apps/dashboard`, website repo merged into `apps/website` **via `git subtree add` (preserving its commit history, not a flat copy)**, `packages/ui-components` → `packages/shared-ui` seeded with the shadcn/ui set, package-scope rename to `@costorah/*` across the board, Turborepo introduced. Sequenced after EP-21–24 so the restructuring PR doesn't also have to carry unrelated feature work.
6. **EP-26 — Design system unification.** Token reconciliation (Part 2's table), dashboard migration from hand-rolled primitives onto the shared shadcn/ui layer, font self-hosting, provider-color constants centralized.
7. **EP-27 — Onboarding wizard completion.** Wire `OnboardingModal` through the real Connect-Provider (EP-23) and usage-ingestion-activation steps.
8. **EP-28 — Transactional email.** One implementation, fixes verification, password reset, and member invites simultaneously.
9. **EP-29 — Website content completion.** Flesh out the 9 stub pages plus the pages your spec lists that don't exist in the Lovable repo at all yet (**Enterprise, Integrations, Roadmap, Careers, Status** are net-new, not migrations).
10. **EP-30 — Unified CI/CD.** Extend the existing GitHub Actions to build/test/typecheck both apps + shared packages via Turborepo's task graph, with separate deploy jobs (Cloudflare for the SSR website, static hosting for the SPA dashboard) triggered from one pipeline.
11. **EP-31 — Billing.** Still fully absent per the prior audit (no Stripe/subscription code anywhere) — correctly sequenced last here since it monetizes a product that isn't self-serve-usable until EP-21–24 land.

---

## Part 8 — Documentation

`CLAUDE.md` has been created at the repository root covering: website architecture, dashboard architecture, target repository structure, the design-system reconciliation table, the authentication/session model (current + target), the workspace/organization data model, this migration roadmap, and the future EP roadmap — intended as the permanent reference for this effort, kept up to date as each EP above lands.

---

## What This Plan Deliberately Does NOT Recommend

- **Does not** force the website onto React Router or the dashboard onto TanStack Start — the SSR/SPA split is the correct architecture for marketing-vs-app, matching every reference product cited.
- **Does not** recommend a flat copy of the website's files into this repo — `git subtree`/history-preserving merge is called out explicitly in EP-25 because you asked for a migration strategy, not a copy-paste.
- **Does not** treat the empty `packages/ui-components` stub as something to build from scratch — it's the intended seed, already scaffolded, just never filled in.
- **Does not** invent a second "workspace" data model alongside the existing `Organization` entity — reuses it, consistent with how Linear/Vercel/Notion model personal + team workspaces as the same underlying entity.
