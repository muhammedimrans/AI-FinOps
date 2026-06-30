# EP-11 Frontend Architecture Review

**Epic:** EP-11 — React Dashboard (AI FinOps Enterprise SaaS Frontend)
**Reviewer:** Engineering Lead
**Review Date:** 2026-06-30
**Commit Reviewed:** `f1ebee5` (feat(ep-11): implement AI FinOps enterprise React dashboard)
**Branch:** `claude/ai-finops-ep-01-s4d42x`

---

## 1. Executive Summary

The EP-11 React dashboard is a production-quality SPA built on React 18, TypeScript strict mode,
Vite 5, TanStack Query v5, TanStack Table v8, Framer Motion v11, Recharts v2, Zustand v5, and
Tailwind CSS v3 with a bespoke glass-morphism design system. The implementation passes TypeScript
compilation with zero errors under the workspace's strictest compiler flags
(`exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`, `noPropertyAccessFromIndexSignature`).
The production build code-splits all seven pages into independent chunks and ships an acceptable
~51KB (gzipped) initial payload.

**Final Decision: APPROVED WITH MINOR CHANGES**

Four confirmed bugs — two HIGH severity — must be resolved in EP-11.5 before EP-12 (live backend
integration) begins. No architectural redesign is warranted. The component architecture, data
fetching strategy, state management model, API contract types, and build tooling are all solid.

---

## 2. Architecture Assessment

### 2.1 Component Architecture — PASS

The application follows a consistent three-tier component hierarchy:

```
App.tsx (router root, lazy imports)
  └── AppLayout (sidebar + header shell, Outlet)
        └── Features (Overview, Analytics, Providers, Models, Projects, Organization, Settings)
              └── Components (MetricCard, ChartCard, ProviderBadge, BudgetBar, EmptyState)
```

- All seven pages are `React.lazy()`-loaded with `Suspense` fallbacks
- Shared UI primitives live in `src/components/` with no feature-specific logic
- Layout primitives (`Sidebar`, `Header`, `AppLayout`) are isolated in `src/layouts/`
- No circular imports detected

### 2.2 Data Fetching — PASS

TanStack Query v5 is used correctly throughout:

- All server state lives in query cache, not Zustand
- `queryKey` arrays include all filter dimensions (`start_date`, `end_date`, `currency`, `granularity`)
  so cache entries are correctly namespaced
- `staleTime: 5 * 60 * 1000` (5 min) prevents unnecessary refetches on tab focus
- `useRecentActivity` uses `refetchInterval: 60_000` for live-updating the activity table
- Mock data path (`USE_MOCK = import.meta.env.DEV`) is correctly gated; Vite removes dead code in
  production builds — mock data files will not be included in the production bundle

The `useFilters()` helper in `useDashboard.ts` correctly reads from `useUIStore` so all hooks
automatically re-query when the user changes date range or currency from the Header.

**Exception:** See BUG-003 — the Analytics page has a local `granularity` state that is not synced
to the store, so granularity tab changes on that page do not trigger API refetches.

### 2.3 State Management — PASS

Zustand v5 with `persist` middleware is the correct choice for UI state at this scale. The store
contains exactly what belongs there:

- `sidebarCollapsed`, `theme` — layout preferences, correctly persisted
- `currency`, `granularity`, `datePreset`, `startDate`, `endDate` — global filter state, correctly
  persisted and used as query key dimensions
- `commandOpen` — ephemeral UI state (correctly NOT persisted via `partialize`)

Server state is not duplicated in Zustand. There is no prop-drilling beyond one level.

### 2.4 API Contract Alignment — PASS

`src/types/api.ts` defines all response shapes with monetary values as `string` (matching Python
Decimal serialization). All `parseFloat()` call sites in chart data transforms are correctly
handling this. The API client in `src/lib/api.ts` uses `AbortSignal.timeout(10_000)` for request
cancellation and throws on non-2xx responses.

The `UsageEventsResponse` type includes `page`, `page_size`, `total` fields from the backend's
cursor pagination contract. The frontend currently ignores these (showing a fixed `limit` from the
mock), which is correct for EP-11 — the live pagination hookup belongs in EP-12.

### 2.5 Build Configuration — PASS

- `manualChunks` in `vite.config.ts` correctly isolates React and TanStack Query into separate
  vendor chunks, reducing cache invalidation scope on application updates
- TypeScript project references (`tsconfig.app.json` / `tsconfig.node.json`) are correctly scoped
- `/// <reference types="vitest" />` is correctly placed in `vite.config.ts`
- The `resolve.alias` uses a string literal `"/src"` (not a Node path), compatible with the
  `tsconfig.node.json` compiler scope

---

## 3. Confirmed Bugs

### BUG-001 — HIGH: `AppLayout.tsx:37` — `location` resolves to `window.location`

```tsx
// AppLayout.tsx:37 — BUG
key={location.pathname}
```

`useLocation` is never imported or called in `AppLayout.tsx`. The identifier `location` therefore
resolves to the browser global `window.location`. `window.location.pathname` does not change
during React Router SPA navigation — the browser history state changes, but the reference stays
the same. As a result, the `motion.div` wrapping `<Outlet />` always receives the same React `key`
and never re-mounts, so the `initial → animate` page transition animation never fires.

**Fix:**
```tsx
// AppLayout.tsx
import { Outlet, useLocation } from "react-router-dom";
// ...
const location = useLocation();
// ...
<motion.div key={location.pathname} ...>
```

This is a one-line import + one-line addition. The `useLocation` hook is already used correctly in
`Header.tsx`, so the pattern is established in the codebase.

---

### BUG-002 — HIGH: `Analytics.tsx:119` — Pagination always frozen at page 0

```tsx
// Analytics.tsx:116-125
const table = useReactTable({
  data: tableData,
  columns,
  state: { sorting, globalFilter: search, pagination: { pageIndex: 0, pageSize } },
  onSortingChange: setSorting,
  getCoreRowModel: getCoreRowModel(),
  getSortedRowModel: getSortedRowModel(),
  getFilteredRowModel: getFilteredRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
});
```

`pagination` is passed as controlled state (`{ pageIndex: 0, pageSize }`) but there is no
`onPaginationChange` handler. In TanStack Table v8 controlled-state mode, `nextPage()` and
`previousPage()` dispatch to `onPaginationChange` which is `undefined`. The buttons never advance
the page.

**Fix:** Remove `pagination` from the controlled `state` object and let TanStack Table manage
pagination internally (uncontrolled for page index), or add a proper `onPaginationChange` handler:

```tsx
const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 25 });

const table = useReactTable({
  data: tableData,
  columns,
  state: { sorting, globalFilter: search, pagination },
  onSortingChange: setSorting,
  onPaginationChange: setPagination,
  // ...
});
```

The `pageSize` select (`setPageSize`) also needs to update the pagination object; with this fix it
will work automatically once `pagination` and `onPaginationChange` are both wired.

---

### BUG-003 — MEDIUM: `Analytics.tsx` — Granularity tabs do not trigger data refetch

```tsx
// Analytics.tsx:44
const [granularity, setGranularity] = useState<Granularity>("daily");
// ...
onClick={() => setGranularity(g)}  // only updates local state
```

```tsx
// useDashboard.ts:20-26
export function useTimeSeries() {
  const { start_date, end_date, currency, granularity } = useFilters(); // reads from store
  return useQuery({ queryKey: ["time-series", ..., granularity], ... });
}
```

The Analytics page maintains its own `granularity` local state that is never pushed to
`useUIStore`. `useTimeSeries()` reads granularity from the store. Clicking the granularity tabs in
Analytics updates the visual selection but never triggers a new API query. The chart always shows
the store's default `"daily"` granularity.

The Overview page solves this correctly:
```tsx
// Overview.tsx:203-204 — CORRECT
onChange={(g) => {
  setGranularity(g);
  useUIStore.getState().setGranularity(g);
}}
```

**Fix:** Apply the same pattern in Analytics — call `useUIStore.getState().setGranularity(g)` on
tab change, or remove the local state and read `granularity` from the store.

---

### BUG-004 — MEDIUM: `Models.tsx:229` — Bubble sizing prop has no effect in Recharts

```tsx
// Models.tsx:229
<Cell
  key={i}
  fill={PROVIDER_COLORS[entry.provider] ?? "#4F46E5"}
  r={Math.max(4, Math.min(20, (entry.z / 500)))}  // r is not a valid Cell prop
/>
```

Recharts `Cell` does not accept an `r` (radius) prop. In a `ScatterChart`, bubble sizing requires
a `ZAxis` component. All scatter points render at Recharts' default size, making the "bubble size
= total spend" feature non-functional.

**Fix:**
```tsx
import { ..., ZAxis } from "recharts";

<ScatterChart ...>
  <ZAxis type="number" dataKey="z" range={[30, 800]} name="Total Spend ($)" />
  ...
  <Scatter data={scatterData}>
    {scatterData.map((entry, i) => (
      <Cell key={i} fill={PROVIDER_COLORS[entry.provider] ?? "#4F46E5"} />
    ))}
  </Scatter>
</ScatterChart>
```

---

## 4. Minor Issues

### MINOR-001: `MetricCard.tsx:39-55` — Dead code: `AnimatedNumber` component is never rendered

The `AnimatedNumber` component using `requestAnimationFrame` is defined but never called. The
MetricCard renders `formattedValue` (a pre-formatted string) directly. Should be removed or wired
in EP-11.5 to animate the numeric value on load.

### MINOR-002: `Sparkline` / `MiniTrendLine` — Division by zero with single-point data

```tsx
// MetricCard.tsx:65
const step = w / (data.length - 1);  // Infinity when data.length === 1
```

When `data` has 0 or 1 points, `step` becomes `Infinity`, point coordinates become `NaN`, and the
SVG polyline silently renders nothing. This is a silent failure, not a crash.

**Fix:** `if (data.length < 2) return null;`

The same pattern exists in `Projects.tsx:17` (`MiniTrendLine`).

### MINOR-003: `Sidebar.tsx:137-140` — Hardcoded user identity

User display name "Mohammed Imran" and role "Platform Admin" are hardcoded. This is expected for
EP-11 (no auth integration yet) and is documented as a known limitation. Must be replaced with
auth context in EP-13 (Authentication UI).

### MINOR-004: `Overview.tsx:161` — Synthetic sparkline data for Total Requests card

```tsx
sparkline={recent7.map((v, i) => i * 2000 + v * 10)}
```

The Total Requests MetricCard receives manufactured sparkline values derived from the cost time
series, not real request count data. Visual-only cosmetic issue. The real values will flow in
automatically once the API returns `total_requests` in the time series response.

### MINOR-005: No React Error Boundary

There is no `ErrorBoundary` component in the application. If a Recharts chart throws during render
(e.g., due to NaN values from unexpected API shapes), the entire page unmounts with a blank white
screen. Given that Recharts is known to be sensitive to data shape edge cases, at least a
per-page error boundary is recommended before EP-12.

---

## 5. Security Review

- No `dangerouslySetInnerHTML` usage anywhere in the codebase
- All API-derived data is rendered through React's JSX (HTML-escaped by default)
- CSV export correctly uses `encodeURIComponent` on the CSV content
- No `eval()` or `new Function()` calls
- `formatCost` passes `currency` to `Intl.NumberFormat` — if localStorage is corrupted with an
  invalid currency code, this throws `RangeError`. Low risk given TypeScript typing and the small
  accepted value set (`USD | EUR | GBP`)
- No secrets or credentials in source code
- `VITE_API_BASE_URL` defaults to `localhost:8000` at build time — the production build must be
  configured with the correct environment variable

---

## 6. TypeScript Compliance

The build passes zero TypeScript errors under these strict flags (from `tsconfig.base.json`):

```json
{
  "exactOptionalPropertyTypes": true,
  "noUncheckedIndexedAccess": true,
  "noPropertyAccessFromIndexSignature": true,
  "noImplicitAny": true,
  "strict": true
}
```

Notable pattern established correctly: `import.meta.env["VITE_API_BASE_URL"]` (bracket notation
required by `noPropertyAccessFromIndexSignature`), `MODELS[i] ?? MODELS[0]!` (non-null assertion
after array index access required by `noUncheckedIndexedAccess`).

---

## 7. Performance Profile

**Build output (production):**
- `vendor` chunk: React + react-dom + react-router-dom → ~157KB gzip ~51KB
- `query` chunk: TanStack Query → ~34KB gzip ~11KB
- `index` chunk: App shell + all features (lazy) → ~165KB gzip ~54KB

**Runtime:**
- 5 concurrent queries on initial load (staggered by browser connection pool)
- All charts use `ResponsiveContainer` — ResizeObserver-based, no direct window event listeners
- `motion.div` with `AnimatePresence` correctly uses GPU-composited transforms (`y`, `opacity`)
- Sidebar collapse animation uses `animate={{ width }}` which triggers layout — acceptable for a
  single element transition

**No critical performance issues identified for the EP-11 scope (mock data).**

---

## 8. EP-12 Readiness Gaps (Not Bugs — Integration Work)

These are not EP-11 bugs but will need attention before or during EP-12:

1. **Authentication gating:** All routes are publicly accessible. EP-12 must add an auth-protected
   route wrapper that redirects to login if no valid session exists.

2. **Error handling in query functions:** The `get<T>()` function throws on non-2xx responses but
   TanStack Query handles retries. The UI currently shows no error state for most components.
   `ChartCard` passes `error` prop but most components don't propagate `query.error`.

3. **Pagination wiring for UsageEventsResponse:** The live backend returns `page`, `page_size`,
   `total` for cursor pagination. The frontend currently uses a fixed `limit=20`. EP-12 must add
   server-side pagination controls.

4. **Real-time connection:** `refetchInterval: 60_000` on recent activity is polling. EP-12 may
   want to evaluate WebSocket or SSE for true real-time feed depending on backend support.

---

## 9. Architecture Decision Records Generated

None required. No architectural deviations from the EP-11 design brief. All decisions are
implementation-level and documented in the respective sections above.

---

## 10. Final Verdict

| Category | Status |
|---|---|
| Component Architecture | PASS |
| Data Fetching & Cache Strategy | PASS |
| State Management | PASS |
| API Contract Alignment | PASS |
| Build Configuration | PASS |
| TypeScript Compliance | PASS |
| Security | PASS |
| Performance | PASS |
| Bug Count (HIGH) | 2 |
| Bug Count (MEDIUM) | 2 |
| Bug Count (MINOR) | 5 |

**VERDICT: APPROVED WITH MINOR CHANGES**

BUG-001 through BUG-004 must be resolved before EP-12 begins. All four are targeted one-to-five
line fixes with no architectural implications. Minor issues (MINOR-001 through MINOR-005) may be
addressed in the same EP-11.5 hardening sprint.

---

*Architecture Review completed 2026-06-30. Next milestone: EP-11.5 Bug Fixes → EP-12 Live Backend Integration.*
