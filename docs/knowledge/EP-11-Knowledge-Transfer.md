# EP-11 Knowledge Transfer

**Epic:** EP-11 — React Dashboard (AI FinOps Enterprise SaaS Frontend)
**Author:** Engineering Lead
**Date:** 2026-06-30
**Status:** Complete (pending EP-11.5 bug fixes)

---

## 1. What Was Built

EP-11 delivers the complete frontend SPA for the AI FinOps platform: a React 18 enterprise
dashboard that visualizes AI API spending across providers, models, projects, and departments.

The application runs in two modes:
- **Development (mock mode):** All API calls return seeded, deterministic mock data. No backend
  required. `pnpm dev` starts the dev server at `http://localhost:5173`.
- **Production:** API calls target the backend at `VITE_API_BASE_URL`. Mock data is tree-shaken
  out of the production bundle entirely.

---

## 2. Repository Structure

```
frontend/
├── src/
│   ├── App.tsx                    # Router root, lazy page imports
│   ├── main.tsx                   # React 18 createRoot, QueryClientProvider, BrowserRouter
│   ├── index.css                  # Global styles, design token CSS vars, component classes
│   ├── test-setup.ts              # Vitest + @testing-library/jest-dom setup
│   │
│   ├── types/
│   │   └── api.ts                 # All API response shapes (mirrors backend JSON)
│   │
│   ├── lib/
│   │   ├── utils.ts               # formatCost, formatNumber, formatTokens, date utils, cn()
│   │   ├── mock-data.ts           # Seeded RNG mock data (DEV only)
│   │   └── api.ts                 # Fetch client, all API functions, mock/real routing
│   │
│   ├── stores/
│   │   └── ui.ts                  # Zustand store: theme, currency, date range, sidebar state
│   │
│   ├── hooks/
│   │   └── useDashboard.ts        # All TanStack Query hooks (useOverview, useTimeSeries, …)
│   │
│   ├── layouts/
│   │   ├── AppLayout.tsx          # Shell: Sidebar + Header + Outlet with page transition
│   │   ├── Sidebar.tsx            # Collapsible sidebar with nav groups
│   │   └── Header.tsx             # Date range, currency, theme toggle, notifications
│   │
│   ├── components/
│   │   ├── MetricCard.tsx         # KPI card with gradient, sparkline, trend indicator
│   │   ├── ChartCard.tsx          # Chart wrapper with title, loading, error, actions
│   │   ├── ProviderBadge.tsx      # Provider pill + PROVIDER_COLORS export
│   │   ├── BudgetBar.tsx          # Animated budget utilization bar
│   │   └── EmptyState.tsx         # Zero-state with icon and description
│   │
│   ├── features/
│   │   ├── Overview.tsx           # KPIs + AreaChart + PieChart + BarChart + Activity table
│   │   ├── Analytics.tsx          # Summary stats + stacked AreaChart + TanStack Table
│   │   ├── Providers.tsx          # Provider cards + comparison BarChart + models table
│   │   ├── Models.tsx             # Leaderboard table + ScatterChart performance matrix
│   │   ├── Projects.tsx           # Budget alert + project card grid with BudgetBar
│   │   ├── Organization.tsx       # Org budget bar + sortable department table
│   │   ├── Settings.tsx           # Tabbed settings: API / Display / Notifications / Data
│   │   └── Placeholder.tsx        # Coming-soon stub for Admin routes
│   │
│   └── services/                  # (empty, reserved for future service layer)
│
├── package.json                   # All dependencies
├── vite.config.ts                 # Vite + Vitest config
├── tailwind.config.ts             # Full design system extension
├── tsconfig.app.json              # Strict app TypeScript config
├── tsconfig.node.json             # Node-scope config for vite.config.ts
├── postcss.config.js              # Autoprefixer
└── .gitignore                     # Excludes dist/, *.tsbuildinfo, .env
```

---

## 3. Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Framework | React | 18.3 |
| Language | TypeScript | 5.5 (strict) |
| Build | Vite | 5.4 |
| Routing | React Router DOM | 6.26 |
| Server state | TanStack Query | 5.56 |
| Table | TanStack Table | 8.20 |
| Client state | Zustand | 5.0 |
| Animation | Framer Motion | 11.11 |
| Charts | Recharts | 2.12 |
| Styling | Tailwind CSS | 3.4 |
| Forms | React Hook Form | 7.53 |
| Validation | Zod | 3.23 |
| Icons | Lucide React | 0.462 |
| Testing | Vitest + Testing Library | 2.1 |
| Package manager | pnpm (workspace) | — |

---

## 4. Data Flow

### 4.1 Global Filter State

All dashboard queries are driven by three global filter dimensions stored in `useUIStore`:

```
Header (date preset / currency)
  ↓ setDateRange / setCurrency
useUIStore (zustand, persisted)
  ↓ startDate, endDate, currency, granularity
useFilters() [in useDashboard.ts]
  ↓ → queryKey includes all dimensions
useQuery (TanStack Query)
  ↓ → api.getXxx({ start_date, end_date, currency })
API client [src/lib/api.ts]
  ↓ DEV? → mock data (delay then return)
  ↓ PROD? → fetch(`${BASE_URL}/v1/dashboard/xxx`)
```

When the user changes the date preset or currency in the Header, Zustand notifies all subscribers.
All six dashboard hooks re-compute their query keys and trigger fresh fetches if the new key is not
in cache.

### 4.2 Mock Data

Mock data is generated in `src/lib/mock-data.ts` using a seeded RNG (`seededRandom(42)`). The seed
ensures consistent data across page reloads in development. Key generators:

- `generateDailyData(90)` — 90 days of daily cost data with weekend factor (0.7), linear growth
  trend, and Gaussian noise
- `getMockProviders()` — 6 providers with preset cost shares (OpenAI 42%, Anthropic 28%, etc.)
- `getMockModels()` — 10 models across providers with per-token pricing
- `getMockProjects()` — 6 projects with budget allocation and utilization
- `getMockOrganization()` — 5 departments with teams and projects
- `getMockRecentActivity(limit)` — live-updating activity feed (60s poll)

**Important:** `USE_MOCK = import.meta.env.DEV` evaluates to a boolean at build time. Vite's
tree-shaker removes the mock branch from the production bundle entirely. Mock data has zero
production footprint.

### 4.3 API Response Types

All monetary values from the backend arrive as `string` (Python `Decimal` serialized to JSON).
The frontend consistently uses `parseFloat()` for arithmetic and `formatCost()` for display.

```typescript
// Correct pattern throughout the codebase:
const total = parseFloat(project.total_cost);  // arithmetic
formatCost(project.total_cost, currency, true); // display
```

Never pass a `Decimal`-sourced string directly to arithmetic operators (`+`, `-`, `*`) without
`parseFloat()` first — string arithmetic in JavaScript silently concatenates.

---

## 5. Design System

### 5.1 Tailwind Tokens

The design system is a Tailwind extension defined in `tailwind.config.ts`. All values are in the
`theme.extend` block to preserve Tailwind defaults:

```
Colors:     app-{bg,card,muted,hover}
            primary-{DEFAULT,hover,light,dim,subtle}
            success/warning/danger/info (each with -dim and -light variants)
            tx-{primary,secondary,muted}
            border-{subtle,DEFAULT,strong}
            openai/anthropic/google/azure/bedrock/cohere

Border radius: rounded-card (12px), rounded-xl (existing)
Shadows:    shadow-card, shadow-card-hover, shadow-glow
Animations: shimmer, fade-in, slide-up
Gradients:  gradient-primary, gradient-success, gradient-card, gradient-shimmer
            (defined in backgroundImage extension)
```

### 5.2 Global Component Classes

Defined in `src/index.css` `@layer components`:

| Class | Usage |
|---|---|
| `.glass-card` | Card surface with backdrop-filter blur and gradient overlay |
| `.metric-gradient-{indigo,emerald,amber,blue,purple}` | MetricCard background variants |
| `.skeleton` | Shimmer loading placeholder |
| `.nav-item` | Sidebar nav link base + active state |
| `.data-table th/td` | Table header/cell styling |
| `.badge` | Provider status/efficiency pill |
| `.btn-primary` | Primary action button |
| `.btn-ghost` | Ghost button (icon buttons) |
| `.btn-outline` | Outlined secondary button |

### 5.3 Provider Colors

```typescript
// src/components/ProviderBadge.tsx — canonical source of truth
export const PROVIDER_COLORS: Record<string, string> = {
  openai:    "#10A37F",
  anthropic: "#D4A574",
  google:    "#4285F4",
  azure:     "#0078D4",
  bedrock:   "#FF9900",
  cohere:    "#9B5DE5",
};
```

Import `PROVIDER_COLORS` from `ProviderBadge.tsx` everywhere provider colors are needed. Do not
duplicate these values.

---

## 6. Routing Structure

```
/                          → Navigate to /dashboard
/dashboard                 → Overview (index)
/dashboard/analytics       → Cost Analytics (TanStack Table + stacked AreaChart)
/dashboard/providers       → Providers (card grid + comparison bar chart)
/dashboard/models          → Models (leaderboard + scatter performance matrix)
/dashboard/projects        → Projects (budget alert + card grid)
/dashboard/organization    → Organization (dept table with sorting)
/users                     → Placeholder (EP-13: Auth UI)
/rbac                      → Placeholder (EP-05 backend exists)
/api-keys                  → Placeholder
/connections               → Placeholder (EP-07: Provider Connections exists)
/audit-logs                → Placeholder
/settings                  → Settings (tabbed form)
```

All routes are wrapped under `AppLayout` (except the `/` redirect). All feature pages are
`React.lazy()` imports — they load as separate JavaScript chunks on first visit, not on app load.

---

## 7. State Persistence

`useUIStore` persists these fields to `localStorage` under the key `"ai-finops-ui"`:

```
sidebarCollapsed, theme, currency, granularity, datePreset, startDate, endDate
```

`commandOpen` is NOT persisted (ephemeral).

**Important:** The persisted `startDate`/`endDate` are ISO date strings that were computed at the
time of the last selection. They do not "roll forward" — if a user selects "Last 30d" on Monday
and returns on Tuesday, the date range still starts from Monday's 30-day window. This is correct
behavior for analytics dashboards (the user selected a specific window, not a rolling window).

If rolling behavior is needed, store the preset name and recompute on load. The infrastructure for
this exists — `datePreset` is persisted — but the recomputation on hydration is not implemented.

---

## 8. Adding a New Dashboard Page

To add a new page (e.g., `/dashboard/costs`):

1. **Create the feature component** in `src/features/CostBreakdown.tsx`
2. **Add the query hook** in `src/hooks/useDashboard.ts` following the existing pattern:
   ```typescript
   export function useCostBreakdown() {
     const { start_date, end_date, currency } = useFilters();
     return useQuery({
       queryKey: ["cost-breakdown", start_date, end_date, currency],
       queryFn: () => api.getCostBreakdown({ start_date, end_date, currency }),
       staleTime: 5 * 60 * 1000,
     });
   }
   ```
3. **Add the API function** in `src/lib/api.ts`
4. **Add the type** in `src/types/api.ts`
5. **Add a lazy import** in `src/App.tsx`
6. **Add a route** in `src/App.tsx` inside the `AppLayout` route group
7. **Add a nav entry** in `src/layouts/Sidebar.tsx` `NAV_ITEMS` array
8. **Add a label** in `src/layouts/Header.tsx` `ROUTE_LABELS` record

---

## 9. Known Bugs (Require Fix in EP-11.5)

| ID | File | Line | Description |
|---|---|---|---|
| BUG-001 | AppLayout.tsx | 37 | `key={location.pathname}` uses `window.location` — page transitions broken |
| BUG-002 | Analytics.tsx | 119 | Pagination frozen at page 0 — no `onPaginationChange` handler |
| BUG-003 | Analytics.tsx | 44 | Granularity local state not synced to store — chart doesn't re-fetch |
| BUG-004 | Models.tsx | 229 | `r` prop on `Cell` has no effect in Recharts — bubble sizes all equal |

See `EP-11-Architecture-Review.md` for the exact fix for each bug.

---

## 10. Known Limitations (Expected for EP-11)

1. **No authentication:** All routes are accessible without login. Authentication UI is EP-13.
   Backend auth (JWT + RBAC) is fully implemented in EP-05.

2. **Admin pages are placeholders:** Users, RBAC, API Keys, Connections, and Audit Logs show a
   "coming soon" UI. The backend endpoints for these exist (EP-05 through EP-10).

3. **Settings do not persist:** The Settings page saves to `console.info` only. Real persistence
   requires an API endpoint or additional localStorage fields.

4. **Hardcoded user identity:** Sidebar footer shows "Mohammed Imran / Platform Admin" hardcoded.
   Replace with auth context in EP-13.

5. **No error boundaries:** A JavaScript exception in any chart component will crash the page.
   Add `ErrorBoundary` wrappers before EP-12.

6. **Pagination not wired to backend:** `UsageEventsResponse` includes `page`, `page_size`, `total`
   from the cursor pagination API but the frontend doesn't use these fields. EP-12 will implement
   server-side pagination for the activity feed.

---

## 11. Development Workflow

```bash
# Install (from workspace root)
pnpm install

# Start dev server (mock data, HMR)
cd frontend && pnpm dev          # → http://localhost:5173

# Type check
pnpm typecheck

# Lint
pnpm lint

# Run tests
pnpm test

# Production build
pnpm build                       # outputs to dist/

# Preview production build
pnpm preview
```

**Environment variables:**
```bash
# .env.local (never commit)
VITE_API_BASE_URL=http://localhost:8000
```

In production, set `VITE_API_BASE_URL` to the backend's public URL at build time. The variable is
embedded in the JavaScript bundle by Vite at build time — it cannot be changed at runtime.

---

## 12. Testing

Tests use Vitest + React Testing Library + jsdom. Test files belong in `src/__tests__/` (not yet
created) or co-located with components as `*.test.tsx`.

Setup file `src/test-setup.ts` imports `@testing-library/jest-dom` for DOM matchers.

Coverage is configured in `vite.config.ts`:
```typescript
coverage: {
  provider: "v8",
  reporter: ["text", "lcov"],
  exclude: ["node_modules/", "src/test-setup.ts"],
}
```

**Note:** No unit tests were written in EP-11. The build passes zero TypeScript errors and all
components render correctly in mock mode. EP-12 should add component tests for the six dashboard
pages before connecting live data.

---

*EP-11 Knowledge Transfer completed 2026-06-30.*
