# EP-11 UI/UX Review

**Epic:** EP-11 — React Dashboard (AI FinOps Enterprise SaaS Frontend)
**Reviewer:** Engineering Lead
**Review Date:** 2026-06-30
**Commit Reviewed:** `f1ebee5`

---

## 1. Executive Summary

The EP-11 dashboard delivers a professional, dark-first B2B SaaS aesthetic with a coherent design
language across all seven pages. The glass-morphism design system, animated transitions, data
density, and information hierarchy are at production level. Several functional UX issues are
identified — most tied to the confirmed code bugs in the Architecture Review — plus a set of
accessibility gaps that must be addressed before the dashboard reaches external users.

**UI/UX Verdict: APPROVED WITH MINOR CHANGES**

The visual design and information architecture are strong. The accessibility gaps (listed below)
are the primary concern for production readiness; they are addressable without redesign.

---

## 2. Design System Consistency

### 2.1 Color System — PASS

The Tailwind design token extension in `tailwind.config.ts` establishes a coherent semantic color
system. Tokens are named for intent, not value:

| Token | Purpose | Value |
|---|---|---|
| `app-bg` | Page background | `#0A0A0F` |
| `app-card` | Card surface | `#12121A` |
| `app-muted` | Muted surface | `#1A1A26` |
| `primary` | Primary action / active state | `#4F46E5` |
| `success` | Positive metric / under-budget | `#10B981` |
| `danger` | Over-budget / error | `#EF4444` |
| `warning` | Approaching limit | `#F59E0B` |
| `tx-primary` | Primary text | `#F8FAFC` |
| `tx-secondary` | Secondary text | `#94A3B8` |
| `tx-muted` | Labels / captions | `#475569` |

Provider color tokens (`openai`, `anthropic`, `google`, `azure`, `bedrock`, `cohere`) are
consistent across `ProviderBadge`, chart series, and cost-share bars on the Providers page.

**No color inconsistencies found.** `PROVIDER_COLORS` is exported from `ProviderBadge.tsx` as the
single source of truth and imported everywhere colors are needed.

### 2.2 Typography — PASS

Inter is loaded from Google Fonts via `@import` in `index.css`. Weight chain: 300, 400, 500, 600,
700. Font scale is consistent — `text-xs` (labels/captions), `text-sm` (body), `text-xl`/`text-2xl`
(metric values), `text-h2` (page headings). Monospace font stack falls back correctly for token
counts, model IDs, and cost values in tables.

**Note:** The Google Fonts `@import` in `index.css` will block rendering until the stylesheet is
fetched. For production, consider moving to `<link rel="preconnect">` in `index.html` and a
`font-display: swap` strategy. Minor performance issue, not a blocking concern.

### 2.3 Spacing and Layout — PASS

All pages use `p-6 space-y-6` as the outer container, creating uniform 24px page padding and
24px vertical rhythm between sections. Grid systems are responsive:
- Cards: `grid-cols-2 lg:grid-cols-4` (KPI cards)
- Project cards: `grid-cols-1 md:grid-cols-2 xl:grid-cols-3`
- Charts: full-width with `ResponsiveContainer`

The sidebar transitions smoothly between 64px (collapsed) and 240px (expanded) via
`motion.aside animate={{ width }}`.

### 2.4 Component Reuse — PASS

Shared components used consistently across all pages:
- `MetricCard` — KPI cards with gradient variants, sparklines, trend indicators
- `ChartCard` — chart wrapper with title, subtitle, loading skeleton, error state, action slot
- `ProviderBadge` — provider pill with colored dot
- `BudgetBar` — animated budget utilization bar
- `EmptyState` — zero-state component with icon and description
- `.skeleton` class — shimmer loading placeholders

No bespoke one-off card/table implementations found.

---

## 3. Page-by-Page Review

### 3.1 Overview (`/dashboard`) — STRONG

The Overview page achieves excellent information density without visual clutter:

**Strengths:**
- Four KPI cards (Total Spend, Total Requests, Token Usage, Avg Cost/Request) provide the right
  top-level metrics for an AI FinOps dashboard
- Trend indicators (`TrendingUp`/`TrendingDown` icons + percentage) correctly invert meaning for
  cost metrics (`trendInverse={false}`) — a cost increase shows red
- Stacked AreaChart for spend trend with provider-colored series gives immediate visual breakdown
- Donut PieChart for provider distribution is appropriately compact
- Horizontal BarChart for top models is an efficient encoding for a ranked list
- Recent Activity auto-refreshes every 60 seconds with a live "pulse" indicator

**Issues:**
- Granularity tabs are visually present but the re-fetch is only triggered when the tabs also
  write to the store — in the current code, Overview correctly calls
  `useUIStore.getState().setGranularity(g)`, so this works correctly on Overview
- The Total Requests sparkline uses synthetic data (see MINOR-004 in Architecture Review) — this
  will be invisible to users but is noted

### 3.2 Cost Analytics (`/dashboard/analytics`) — GOOD, FUNCTIONAL BUG

**Strengths:**
- Summary stat row (Total Spend, Avg/Min/Max Cost per Request) gives a quick statistical view
- TanStack Table with sortable columns, global search, pagination, and CSV export is a complete
  data exploration tool for power users
- Stacked AreaChart with per-provider breakdown is correctly using `stackId="1"`

**Issues:**
- **Granularity tabs do not work** (BUG-003 from Architecture Review) — changing from Daily to
  Weekly to Monthly has no visual effect on the chart
- **Pagination buttons do not advance pages** (BUG-002 from Architecture Review) — clicking → does
  nothing because `pageIndex` is frozen at 0

These are functional regressions that users will encounter on first use.

### 3.3 Providers (`/dashboard/providers`) — STRONG

**Strengths:**
- Provider card grid with cost share bar, animated fill (Framer Motion), active badge, and model
  count is an excellent data card design
- Metric toggle (Cost / Requests / Tokens) on the comparison BarChart is a smart space-saving
  interaction
- Provider-colored bars on the chart correctly use `PROVIDER_COLORS`
- Models table at the bottom provides drill-down without navigation

**Issues:** None beyond the confirmed bugs.

### 3.4 Models (`/dashboard/models`) — GOOD, FUNCTIONAL BUG

**Strengths:**
- Medal leaderboard (🥇🥈🥉) is a strong visual metaphor for cost ranking
- `EfficiencyBadge` (Efficient / Moderate / Pricey / Premium) based on percentile rank is an
  immediately actionable classification
- ScatterChart intended as a "performance matrix" (cost vs. requests, bubble = total spend) is a
  sophisticated visualization choice for an engineering audience

**Issues:**
- **Scatter bubbles are all the same size** (BUG-004 from Architecture Review) — the `r` prop on
  `Cell` has no effect in Recharts. The chart is visually functional but the bubble sizing
  that encodes total spend is non-functional
- The quadrant labels ("High Value", "Premium", "Monitor", "Optimize") are meaningful but the
  quadrant boundaries are not anchored to any computed median — they are absolute visual quadrants.
  This is acceptable for EP-11 but worth noting for EP-12

### 3.5 Projects (`/dashboard/projects`) — STRONG

**Strengths:**
- Budget alert banner (danger for over-budget, warning for approaching limit) provides immediate
  triage information before the user reads any card
- Project card grid with BudgetBar, trend sparkline, and top model tags is information-dense and
  scannable
- `MiniTrendLine` with green/red coloring correctly encodes trend direction

**Issues:**
- `MiniTrendLine` will silently render nothing if `trend_data` has fewer than 2 points (see
  MINOR-002 in Architecture Review)

### 3.6 Organization (`/dashboard/organization`) — STRONG

**Strengths:**
- Organization-level budget overview bar above the department table provides context for the
  per-department numbers
- Sortable department table with `ArrowUpDown`/`ArrowUp`/`ArrowDown` icons is correctly
  interactive
- Staggered row animation (`delay: i * 0.04`) is subtle and professional

**Issues:** None.

### 3.7 Settings (`/settings`) — PASS

**Strengths:**
- Four-tab layout (API / Display / Notifications / Data) is well-organized
- React Hook Form + Zod validation on the API tab gives proper field-level error feedback
- Toggle component with accessible `role="switch"` and `aria-checked` is correctly implemented
- Theme switcher, currency selector, and notification toggles all function correctly

**Issues:**
- The Settings form saves to `console.info` only — no persistence mechanism exists yet. This is
  expected for EP-11 but should be documented as a known limitation

---

## 4. Navigation and Information Architecture

### 4.1 Sidebar Navigation — PASS

The three-group navigation (Analytics / Admin / System) is correctly structured for the application
scope. The active state indicator (`layoutId="nav-indicator"` animated underline) is a polished
interaction.

**Observation:** The Admin section (Users, RBAC, API Keys, Connections, Audit Logs) links to
Placeholder pages. This is correct for EP-11. The navigation structure anticipates the full
platform without exposing incomplete features as broken pages.

### 4.2 Header Controls — PASS

The Header provides global controls that affect all dashboard queries:
- Date preset dropdown (Today / 7d / 30d / 90d / This month) — correctly updates `useUIStore`
  → all queries reactively re-fetch
- Currency selector (USD / EUR / GBP) — correctly updates `useUIStore`

**Observation:** The Header date pickers close on outside-click is not implemented — the dropdown
stays open until a selection is made or the button is clicked again. Low priority.

### 4.3 Page Transitions — BLOCKED BY BUG-001

The `motion.div` page transition in `AppLayout.tsx` is broken (BUG-001 — `window.location` used
instead of `useLocation()`). Pages appear instantly without the intended `opacity: 0 → 1, y: 6 → 0`
transition. After BUG-001 is fixed, transitions will work without further changes.

---

## 5. Accessibility Review

### 5.1 Keyboard Navigation — PARTIAL FAIL

**What works:**
- `:focus-visible` ring is defined in `index.css` (`outline: 2px solid #4F46E5`) and will apply
  to native focusable elements (buttons, inputs, selects, links)
- Settings toggles have `role="switch"` and `aria-checked`
- Sidebar collapse button has `aria-label`

**What is missing:**
- The Header date dropdown and currency dropdown have no keyboard dismiss (Escape key) and no
  `aria-expanded` attribute on the trigger button
- Table sort headers are `<th>` with `onClick` but have no `tabIndex="0"` or keyboard activation
  handler — cannot be activated by keyboard users
- The Provider card grid and Project card grid have `cursor-pointer` but are `<div>` elements,
  not `<button>` or `<a>` — they are not keyboard-accessible (no `tabIndex`, no `onKeyDown`)
- `NavLink` from react-router-dom renders as `<a>`, so sidebar navigation is keyboard-accessible

### 5.2 Screen Reader Support — PARTIAL FAIL

**What works:**
- Semantic `<header>`, `<nav>`, `<main>`, `<aside>` elements are used in the layout
- `<table>` with `<thead>` / `<th>` / `<tbody>` / `<td>` structure is correct
- Button `aria-label` attributes on icon-only buttons (theme toggle, notifications)

**What is missing:**
- Live region (`aria-live="polite"`) for the Recent Activity auto-refresh — screen readers are
  not notified when new rows appear
- Chart content (`AreaChart`, `PieChart`, `BarChart`, `ScatterChart`) has no text alternative.
  Recharts renders SVG which is opaque to screen readers without `aria-label` or `<title>` elements
- `ProviderBadge` colored dots have no `aria-hidden="true"` — screen readers may announce the
  empty decorative span

### 5.3 Color Contrast — PASS

Using the design token values:
- `tx-primary (#F8FAFC)` on `app-bg (#0A0A0F)` — contrast ratio ~18:1 (WCAG AAA)
- `tx-secondary (#94A3B8)` on `app-card (#12121A)` — contrast ratio ~7.3:1 (WCAG AA)
- `tx-muted (#475569)` on `app-bg (#0A0A0F)` — contrast ratio ~5.1:1 (WCAG AA for large text;
  fails AA for normal text at 14px)

**Note:** `tx-muted` used for 10px–12px labels and captions does not meet WCAG AA contrast ratio
for small text (requires 4.5:1 at body scale — at 10px/12px `tx-muted` is borderline). This is a
common B2B SaaS trade-off. Consider lightening `tx-muted` to `#64748B` for better contrast at
small sizes.

### 5.4 ARIA Roles on Interactive Non-Button Elements

As noted in 5.1, clickable `<div>` and `<motion.div>` elements on Project cards and Provider cards
are not keyboard-accessible. While this is a common pattern in B2B dashboards (where the primary
interaction is visual scanning, not action), it should be addressed before the dashboard is
presented to screen-reader users.

---

## 6. Responsive Design

The application targets desktop/laptop viewports (1024px+). Mobile is not in scope for EP-11.

**Reviewed breakpoints:**
- `lg:grid-cols-4` correctly collapses to `grid-cols-2` on narrower viewports
- Sidebar collapse behavior works at all widths
- Table overflow is handled with `overflow-x-auto` on all table containers
- Header controls may overflow on very narrow screens (< 768px) — acceptable for B2B dashboard

---

## 7. Animation and Motion

All animations use GPU-composited properties (`opacity`, `transform`) via Framer Motion. No
layout-thrashing `width`/`height` animations except the sidebar collapse — which is intentional
and acceptable for a single-element transition.

- Page skeleton loading states use CSS `shimmer` animation — no FOUC
- Staggered card entry animations (`delay: i * 0.05–0.08`) are appropriately subtle
- `whileHover={{ y: -2 }}` lift on cards is a polished micro-interaction

**Accessibility note:** There is no `prefers-reduced-motion` media query applied. Users who have
set `prefers-reduced-motion: reduce` in their OS will still see all animations. For EP-12, wrap
Framer Motion's global configuration with:
```tsx
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
```
and conditionally disable transitions.

---

## 8. Summary of UI/UX Issues

| ID | Severity | Location | Issue |
|---|---|---|---|
| BUG-001 | HIGH | AppLayout.tsx | Page transitions broken (window.location vs useLocation) |
| BUG-002 | HIGH | Analytics.tsx | Pagination buttons non-functional |
| BUG-003 | MEDIUM | Analytics.tsx | Granularity tabs don't trigger refetch |
| BUG-004 | MEDIUM | Models.tsx | Scatter bubble sizing non-functional |
| UX-001 | MEDIUM | All | No keyboard activation for sortable table headers |
| UX-002 | MEDIUM | Projects, Providers | Clickable card divs not keyboard accessible |
| UX-003 | MEDIUM | All charts | No screen reader alternative for chart content |
| UX-004 | LOW | Header | Dropdowns lack Escape key dismiss and aria-expanded |
| UX-005 | LOW | Recent Activity | No aria-live region for auto-refreshing content |
| UX-006 | LOW | Global | No prefers-reduced-motion support |
| UX-007 | LOW | Typography | tx-muted at 10–12px is borderline on contrast |
| UX-008 | INFO | Google Fonts | @import blocks render — consider preconnect link |

---

## 9. Final Verdict

The visual design, component quality, and information architecture are production-grade for a B2B
SaaS platform. The functional bugs (BUG-001 through BUG-004) must be resolved in EP-11.5. The
accessibility gaps (UX-001 through UX-006) should be addressed in EP-11.5 or as a dedicated
accessibility sprint before any external user access.

**VERDICT: APPROVED WITH MINOR CHANGES**

---

*UI/UX Review completed 2026-06-30.*
