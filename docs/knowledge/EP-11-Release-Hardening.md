# EP-11.5 Release Hardening — Knowledge Transfer

**Sprint:** EP-11.5 Frontend Release Hardening  
**Date:** 2026-06-30  
**Status:** Complete — Ready for EP-12  
**Test result:** 27 passed, 0 failed

---

## Context

EP-11 delivered the full AI FinOps React dashboard (7 pages, glass-morphism
design system, mock data layer). The combined architecture and production
readiness review returned **APPROVED WITH MINOR CHANGES** with 4 confirmed
bugs (2 HIGH, 2 MEDIUM) and 5 minor issues. This sprint resolves all items
before EP-12 (Live Backend Integration) begins.

**Rules applied throughout:**
- No frontend redesign
- No backend code changes
- No API changes
- No new features introduced
- All fixes minimal and targeted

---

## RH-01 — Page Transitions Broken (HIGH)

**Root cause:** `AppLayout.tsx` used `key={location.pathname}` on `motion.div`
where `location` resolved to the global `window.location` object (always the
same reference), not React Router's location. Framer Motion never saw a key
change between navigations.

**Fix:** Added `useLocation` from `react-router-dom`. Called
`const location = useLocation()` inside the component body.

**File:** `frontend/src/layouts/AppLayout.tsx`  
**Change:** 2 lines (import + call)

---

## RH-02 — Analytics Pagination Frozen (HIGH)

**Root cause:** `useReactTable` received `state: { pagination }` (controlled
mode) but no `onPaginationChange` handler. TanStack Table v8 dispatches all
pagination mutations to `onPaginationChange`. Without it, calling
`table.nextPage()` or `table.previousPage()` was a no-op — the state never
updated.

**Fix:** Converted to a unified `PaginationState` state object and wired
`onPaginationChange: setPagination`.

**File:** `frontend/src/features/Analytics.tsx`  
**Change:** ~8 lines

---

## RH-03 — Granularity Sync Missing (MEDIUM)

**Root cause:** Analytics granularity tabs called `setGranularity(g)` (local
component state only). `useTimeSeries()` reads granularity from the Zustand
`useUIStore`, which was never updated. The chart displayed Daily data regardless
of which tab was selected.

**Fix:** On tab click, also call `useUIStore.getState().setGranularity(g)` to
write the selection into the store and trigger a query re-fetch.

**File:** `frontend/src/features/Analytics.tsx`  
**Change:** 1 line inside onClick handler

---

## RH-04 — Scatter Chart Bubble Sizing (MEDIUM)

**Root cause:** `<Cell r={...} />` inside a Recharts `ScatterChart`. The `r`
prop is not a valid Recharts prop on `Cell` — bubble sizing in scatter charts
is controlled by `ZAxis`. All bubbles rendered at identical default size,
making the performance matrix meaningless.

**Fix:** Added `<ZAxis type="number" dataKey="z" range={[40, 800]} name="Total Spend ($)" />`
inside the `ScatterChart`. Removed the invalid `r` prop from `Cell`.

**File:** `frontend/src/features/Models.tsx`  
**Change:** Import + 1 component addition, removed invalid prop

---

## RH-05 — Global Error Boundaries (HIGH)

**Added:** `frontend/src/components/ErrorBoundary.tsx` — React class component
with `getDerivedStateFromError`, `override componentDidCatch` (logs to
console), and fallback UI (AlertTriangle icon, error message, "Try again"
button).

**Wired:** Every `<Suspense>` in `App.tsx` is now wrapped:
```tsx
<ErrorBoundary><Suspense fallback={<PageFallback />}><Page /></Suspense></ErrorBoundary>
```

Supports custom `fallback` prop. Reset clears `hasError` and lets React
re-render the children.

---

## RH-06/07 — Loading & Empty State Audit

**Result:** All pages already have skeleton loaders tied to `isLoading` from
TanStack Query. MetricCard has a dedicated `loading` prop.

**Gaps found and fixed:**
- `Providers.tsx`: grid rendered empty when no providers. Added `<EmptyState
  icon={Plug} />`.
- `Models.tsx` leaderboard: search returning no results showed an empty tbody
  with no message. Added inline empty-row message.

No layout shift issues identified — all skeletons match final layout dimensions.

---

## RH-08 — Accessibility (Keyboard + Motion)

### Reduced Motion

Added `<MotionConfig reducedMotion="user">` at the root in `main.tsx`. This
wraps the entire app and instructs Framer Motion to respect the OS-level
`prefers-reduced-motion: reduce` media query. No per-component changes needed.

### Sort Header Keyboard Navigation

- `Organization.tsx`: Sortable `<th>` elements now have `tabIndex={0}`,
  `onKeyDown` (Enter/Space triggers sort), `role="columnheader"`, and
  `aria-sort="ascending|descending|none"`.
- `Analytics.tsx`: TanStack Table header cells now receive `tabIndex={0}`,
  `onKeyDown`, and `aria-sort` attributes.

---

## RH-09 — Responsive Audit

**Result:** Pass. All card grids use `grid-cols-2 lg:grid-cols-4` or
`grid-cols-1 md:grid-cols-2 xl:grid-cols-3`. All tables are wrapped in
`overflow-x-auto`. Sidebar is fixed-width desktop-only (EP-12 gap: mobile
sidebar not implemented).

---

## RH-10 — Performance Audit

**Result:** Pass.
- All pages lazy-loaded via `React.lazy()` with `Suspense`
- `useMemo` used in Analytics (tableData, columns) and Models (sorted, filtered)
- TanStack Query 5-min staleTime + 15-sec refetch interval
- Vendor/query chunk splitting in `vite.config.ts`
- No redundant renders identified — Recharts charts use `ResponsiveContainer`
  correctly

---

## MINOR-001 — Dead AnimatedNumber Code

Removed entire `AnimatedNumber` function from `MetricCard.tsx` (defined but
never called). Also removed dead `numericValue` variable and unused
`useState`, `useEffect`, `useRef` imports.

---

## MINOR-002 — Sparkline Division by Zero

`step = w / (data.length - 1)` evaluates to `Infinity` when `data.length === 1`,
producing NaN SVG coordinates and a silently broken chart.

**Fixed in:**
- `MetricCard.tsx` → `Sparkline`: guard changed to `if (data.length < 2) return null`
- `Projects.tsx` → `MiniTrendLine`: added `if (nums.length < 2) return null`

---

## Regression Tests Added

`frontend/src/__tests__/`:

| File | Coverage |
|------|----------|
| `sparkline.test.ts` | MINOR-002: division-by-zero guard, flat data, empty/single arrays |
| `utils.test.ts` | formatCost, formatNumber, formatTokens, trendIcon, modelDisplayName, providerDisplayName |
| `ErrorBoundary.test.tsx` | RH-05: renders/catches errors, fallback UI, retry reset, custom fallback |

**Run:** `pnpm test` → 27 passed, 0 failed

---

## Build Verification

| Step | Result |
|------|--------|
| `pnpm typecheck` | ✓ Pass (0 errors) |
| `pnpm test` | ✓ 27/27 passed |
| `pnpm build` | ✓ Pass — 22 chunks, 8.92s |
| `pnpm lint` | ⚠ 58 pre-existing errors (see below) |

---

## Pre-Existing Lint Backlog (Out of EP-11.5 Scope)

ESLint reports 58 errors that existed before EP-11.5. These are documented
here for EP-12 prioritization. They do NOT affect runtime correctness — the
TypeScript compiler (`tsc -b`) passes with 0 errors.

**Categories:**

1. **Recharts `any` typed callbacks** — All custom tooltip/formatter functions
   use `({ active, payload }: any)`. Pattern appears in Overview, Models,
   Analytics. Fix: define typed interfaces matching Recharts callback signatures.

2. **Unused imports** — `Filter` in Analytics, `Legend` in Providers,
   `DollarSign` in Settings, `Search`/`RefreshCw` in Header, `Activity` in
   Sidebar. Fix: remove unused imports.

3. **Unused variables** — `activeProviders` in Overview, `apiSchema` in
   Settings, `isNear` in Organization (local variable assigned but not used
   in the rendered JSX). Fix: remove or wire up.

4. **`[...Array(n)]` spread** — ESLint flags `any[]` spread in skeleton
   generators. Pattern: `[...Array(4)].map(...)`. Fix: use
   `Array.from({ length: 4 }, ...)` consistently (already used in most places).

5. **Settings.tsx** — `no-misused-promises` on an async `onSubmit` passed to
   an `onClick`. Fix: wrap in `void` or move to `handleSubmit`.

**Recommendation:** Fix lint backlog in EP-12 sprint setup before adding new
pages — run `pnpm lint:fix` first to auto-fix 3 errors, then address the rest
manually.

---

## Files Changed in EP-11.5

| File | Change |
|------|--------|
| `src/layouts/AppLayout.tsx` | RH-01: useLocation fix |
| `src/features/Analytics.tsx` | RH-02 + RH-03: pagination + granularity sync + keyboard a11y |
| `src/features/Models.tsx` | RH-04: ZAxis bubble sizing + empty search state |
| `src/features/Projects.tsx` | MINOR-002: MiniTrendLine guard |
| `src/features/Providers.tsx` | RH-07: empty state |
| `src/features/Organization.tsx` | RH-08: keyboard sort headers + aria-sort |
| `src/components/MetricCard.tsx` | MINOR-001 + MINOR-002: dead code + Sparkline guard |
| `src/components/ErrorBoundary.tsx` | RH-05: NEW — global error boundary |
| `src/App.tsx` | RH-05: wrap all routes with ErrorBoundary |
| `src/main.tsx` | RH-08: MotionConfig reducedMotion="user" |
| `src/__tests__/sparkline.test.ts` | NEW — regression test |
| `src/__tests__/utils.test.ts` | NEW — regression test |
| `src/__tests__/ErrorBoundary.test.tsx` | NEW — regression test |
