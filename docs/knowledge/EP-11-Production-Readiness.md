# EP-11 Production Readiness Review

**Epic:** EP-11 — React Dashboard (AI FinOps Enterprise SaaS Frontend)
**Reviewer:** Engineering Lead
**Review Date:** 2026-06-30
**Commit Reviewed:** `f1ebee5`

---

## 1. Executive Summary

This review assesses whether the EP-11 frontend is ready to connect to the live EP-10 backend and
be deployed to a production environment. The assessment covers build integrity, security posture,
observability, error handling, performance, and deployment configuration.

**Overall Verdict: NOT READY FOR PRODUCTION AS-IS**
**Ready for EP-12 (Live Backend Integration) after EP-11.5 bug fixes: YES**

The frontend is not yet a standalone production artifact — it requires backend integration (EP-12),
authentication (EP-13), and several hardening items listed below. However, it is ready to be
connected to the live backend in a staging environment once the four confirmed bugs are fixed.

---

## 2. Checklist

### 2.1 Build Integrity

| Check | Status | Notes |
|---|---|---|
| TypeScript compilation (0 errors) | PASS | `tsc -b && vite build` exits 0 |
| ESLint (0 warnings) | UNKNOWN | `pnpm lint` not verified in CI |
| Production bundle generates | PASS | `dist/` contains all assets |
| Code splitting (7 lazy chunks) | PASS | All feature pages are separate chunks |
| Source maps generated | PASS | `sourcemap: true` in vite.config.ts |
| `dist/` excluded from git | PASS | `.gitignore` contains `dist/` |
| `*.tsbuildinfo` excluded from git | PASS | `.gitignore` contains `*.tsbuildinfo` |
| `.env` excluded from git | PASS | `.gitignore` contains `.env*` |
| Mock data tree-shaken in prod | PASS | `import.meta.env.DEV` is compile-time false |

### 2.2 Security

| Check | Status | Notes |
|---|---|---|
| No secrets in source code | PASS | No credentials, tokens, or API keys found |
| No `dangerouslySetInnerHTML` | PASS | All content rendered via JSX |
| No `eval()` / `new Function()` | PASS | Not found in any source file |
| XSS protection | PASS | React escapes all JSX string rendering |
| CSV export sanitization | PASS | `encodeURIComponent` used correctly |
| `VITE_API_BASE_URL` configurable | PASS | Defaults to localhost, override via env |
| Content Security Policy (CSP) | MISSING | No CSP meta tag or header configuration |
| Subresource Integrity (SRI) | MISSING | Google Fonts loaded without SRI |
| Authentication gating | MISSING | All routes publicly accessible |
| CORS | N/A | Handled by backend; frontend makes fetch to same-origin via proxy |

**CSP Gap Detail:**
The frontend loads Inter from `fonts.googleapis.com` via `@import` in `index.css`. A strict CSP
would need to whitelist `fonts.googleapis.com` and `fonts.gstatic.com`. Without a CSP, any
injected script tag in the HTML document could execute. For a B2B SaaS dashboard serving internal
users, this is lower risk than a public-facing consumer product, but should be addressed before
external user access.

### 2.3 Error Handling

| Check | Status | Notes |
|---|---|---|
| API 4xx/5xx raises Error | PASS | `get<T>()` throws on `!res.ok` |
| TanStack Query retry | PASS | Default 3x exponential backoff |
| ChartCard shows error state | PARTIAL | `ChartCard` has `error` prop; most call sites pass `null` |
| Query error propagation | FAIL | Most pages don't propagate `query.error` to UI |
| React Error Boundary | MISSING | No `ErrorBoundary` component exists |
| Page-level crash handling | FAIL | Recharts exception = blank white screen |
| AbortSignal timeout | PASS | 10s timeout on all fetch requests |
| Network failure feedback | PARTIAL | TanStack Query retries then shows stale data |

**Error Boundary Gap Detail:**
Recharts 2.x is known to throw `TypeError` when given NaN values or empty arrays in certain chart
configurations. Without an Error Boundary, a single chart failure crashes the entire page
(including the KPI cards, activity table, and navigation). An `ErrorBoundary` wrapper per feature
page would contain the blast radius to the failing section.

### 2.4 Observability

| Check | Status | Notes |
|---|---|---|
| Structured logging (frontend) | MISSING | No client-side error reporting |
| Error tracking (Sentry/etc.) | MISSING | No error capture integration |
| Performance monitoring | MISSING | No Web Vitals tracking |
| User analytics | MISSING | No page view or event tracking |
| React Query DevTools | PRESENT | `@tanstack/react-query-devtools` in dependencies |

**Note:** Frontend observability is not a blocker for EP-12 staging. It must be addressed before
any production deployment to external users. Minimum viable: integrate `window.onerror` capture
that sends to the backend's structured logging endpoint (already available from EP-02).

### 2.5 Performance

| Check | Status | Notes |
|---|---|---|
| Vendor chunk split | PASS | React + react-router-dom isolated |
| Query chunk split | PASS | TanStack Query isolated |
| Lazy-loaded pages | PASS | 7 lazy chunks, load on first navigation |
| Image assets | N/A | No images — icons are Lucide React (SVG inline) |
| Font loading strategy | PARTIAL | `@import` blocks render; should be `<link rel="preconnect">` |
| Tree shaking | PASS | Vite production build verifies |
| Gzip build size | ACCEPTABLE | ~51KB vendor + ~54KB index gzip |
| Core Web Vitals (estimated) | NOT MEASURED | No real measurement; mock data loads are instant |

**Bundle Size Breakdown (production build):**

| Chunk | Raw | Gzip |
|---|---|---|
| vendor (React, router, DOM) | ~157KB | ~51KB |
| query (TanStack Query) | ~34KB | ~11KB |
| index (app shell) | ~165KB | ~54KB |
| Lazy feature chunks (×7) | ~45KB each (est.) | — |

Total initial load: ~116KB gzip. This is excellent for a full-featured SaaS dashboard. Feature
chunks load on-demand.

### 2.6 Deployment Configuration

| Check | Status | Notes |
|---|---|---|
| `VITE_API_BASE_URL` env var | CONFIGURED | Defaults to `http://localhost:8000` |
| SPA routing (`history` mode) | REQUIRES CONFIG | Backend/CDN must serve `index.html` for all routes |
| Static asset hosting | READY | `dist/` contains all assets with content-addressed filenames |
| Cache headers strategy | NOT CONFIGURED | `dist/assets/` should have long-lived cache headers |
| `dist/` in git | PASS | Correctly ignored |

**SPA Routing Gap:**
React Router uses HTML5 History API (`BrowserRouter`). Any navigation to `/dashboard/analytics`
via direct URL or browser refresh will return a 404 from a naive static server unless configured
to serve `index.html` for all routes.

**Nginx configuration example:**
```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

**Cache strategy recommendation:**
```
dist/index.html          → Cache-Control: no-cache
dist/assets/*.js         → Cache-Control: max-age=31536000, immutable
dist/assets/*.css        → Cache-Control: max-age=31536000, immutable
```
Vite generates content-addressed asset filenames, so `immutable` caching is safe for JS/CSS files.

---

## 3. Hardening Plan (EP-11.5)

These items must be addressed before EP-12 begins connecting live data:

### Required (Blocking EP-12)

**H-001 — Fix BUG-001: AppLayout `useLocation`**
- File: `src/layouts/AppLayout.tsx:37`
- Add `import { useLocation } from "react-router-dom"` and `const location = useLocation()`
- Effort: 5 minutes

**H-002 — Fix BUG-002: Analytics pagination**
- File: `src/features/Analytics.tsx:119`
- Add `onPaginationChange` handler and remove frozen `pageIndex: 0` from controlled state
- Effort: 15 minutes

**H-003 — Fix BUG-003: Analytics granularity sync**
- File: `src/features/Analytics.tsx:44`
- Call `useUIStore.getState().setGranularity(g)` on granularity tab change
- Effort: 5 minutes

**H-004 — Fix BUG-004: Scatter chart ZAxis**
- File: `src/features/Models.tsx`
- Add `<ZAxis type="number" dataKey="z" range={[30, 800]} />` to ScatterChart
- Remove `r` prop from `Cell` elements
- Effort: 10 minutes

**H-005 — Add React Error Boundaries**
- Create `src/components/ErrorBoundary.tsx`
- Wrap each feature page in `App.tsx` with `<ErrorBoundary fallback={<PageError />}>`
- Effort: 30 minutes

### Recommended (Before External User Access)

**H-006 — Keyboard accessibility for sort headers and card grids**
- Add `tabIndex={0}` and `onKeyDown` to sortable `<th>` elements
- Convert clickable `<div>` cards to `<button>` or add `role="button"` + keyboard handlers
- Effort: 2 hours

**H-007 — Chart screen reader alternatives**
- Add `aria-label` or `<desc>` to SVG chart elements
- Add `aria-live="polite"` to the Recent Activity table
- Effort: 1 hour

**H-008 — Content Security Policy**
- Add CSP meta tag to `index.html` or configure via deployment headers
- Whitelist: `'self'`, `fonts.googleapis.com`, `fonts.gstatic.com`
- Effort: 30 minutes

**H-009 — Font loading optimization**
- Move Google Fonts `@import` from `index.css` to `<link rel="preconnect">` in `index.html`
- Add `font-display: swap` via Google Fonts URL parameter
- Effort: 15 minutes

**H-010 — Fix sparkline division-by-zero edge case**
- File: `src/components/MetricCard.tsx:65`, `src/features/Projects.tsx:17`
- Guard: `if (data.length < 2) return null`
- Effort: 5 minutes

**H-011 — Remove dead `AnimatedNumber` code or wire it**
- File: `src/components/MetricCard.tsx:39-55`
- Either use `AnimatedNumber` in the value render or delete the component
- Effort: 15 minutes

**H-012 — `prefers-reduced-motion` support**
- Detect via `window.matchMedia("(prefers-reduced-motion: reduce)")` and pass to Framer Motion
  `MotionConfig` at the app root
- Effort: 30 minutes

---

## 4. EP-12 Integration Readiness

Once EP-11.5 bug fixes are applied, the frontend is ready for EP-12 (Live Backend Integration):

| Integration Point | Frontend Status | EP-12 Work Required |
|---|---|---|
| `GET /v1/dashboard/overview` | Type-aligned, mock tested | Set `VITE_API_BASE_URL`, validate JSON shape |
| `GET /v1/dashboard/time-series` | Type-aligned, granularity param present | Wire backend granularity endpoint |
| `GET /v1/dashboard/providers` | Type-aligned | Validate response shape |
| `GET /v1/dashboard/models` | Type-aligned | Validate response shape |
| `GET /v1/dashboard/projects` | Type-aligned | Validate response shape |
| `GET /v1/dashboard/organization` | Type-aligned | Validate response shape |
| `GET /v1/usage/events` | Type-aligned, limit param present | Add server-side pagination |
| Authentication | Not implemented | Add auth token header injection in `api.ts` |
| Error states | Partial | Complete error propagation from `query.error` to UI |

The switch from mock to live data is a single-line change:
```typescript
// src/lib/api.ts:25
const USE_MOCK: boolean = import.meta.env.DEV;
// In staging/production: set VITE_API_BASE_URL and deploy with `pnpm build`
// Vite will set import.meta.env.DEV to false, disabling all mock paths
```

No code changes are required to switch from mock to live — only the environment variable.

---

## 5. Production Deployment Checklist

The following checklist applies when the dashboard is first deployed to a real production
environment (post EP-12):

- [ ] `VITE_API_BASE_URL` set to production backend URL at build time
- [ ] `pnpm build` produces zero TypeScript errors and zero ESLint warnings
- [ ] `dist/index.html` served for all routes (SPA fallback configured)
- [ ] `dist/assets/` configured with `Cache-Control: max-age=31536000, immutable`
- [ ] CSP headers configured (H-008)
- [ ] Error tracking (Sentry or equivalent) integrated
- [ ] React Error Boundaries in place (H-005)
- [ ] Authentication gating on all protected routes
- [ ] HTTPS enforced (backend concern, confirm with infrastructure)
- [ ] Google Fonts fallback strategy in place for offline/intranet deployments

---

## 6. Summary

The EP-11 frontend is a complete, high-quality SPA implementation. Its production-readiness gaps
fall into three categories:

1. **Bugs to fix now (EP-11.5):** BUG-001 through BUG-004 — small targeted fixes, ~45 minutes total
2. **Hardening before external users:** Error boundaries, accessibility, CSP, font loading — ~5 hours
3. **Integration work (EP-12):** Backend API connection, auth token injection, error state propagation

**Decision: Proceed to EP-11.5 hardening sprint, then EP-12.**

---

*Production Readiness Review completed 2026-06-30.*
