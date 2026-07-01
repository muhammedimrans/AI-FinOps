# Costorah Frontend

React + TypeScript + Vite dashboard for the Costorah AI cost observability platform.

## Stack

- **React 18** + **TypeScript** (strict, `exactOptionalPropertyTypes` enabled)
- **Vite** for dev server / build
- **Tailwind CSS** — design tokens driven by CSS variables so themes switch at runtime with no rebuild (see `src/index.css`)
- **Zustand** for client state (`src/stores`)
- **TanStack Query** for server state / data fetching
- **React Router** for routing
- **Framer Motion** for animation
- **Recharts** for charts
- **Vitest** for unit tests

## Getting started

```bash
pnpm install
cp .env.example .env.development   # then adjust VITE_API_BASE_URL / VITE_ENABLE_MOCKS
pnpm --filter @ai-finops/frontend dev
```

The app expects a running backend at `VITE_API_BASE_URL` (see `.env.example`). Set
`VITE_ENABLE_MOCKS=true` to develop against generated mock data instead of a live backend.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Type-check (`tsc -b`) then production build |
| `npm run preview` | Preview a production build locally |
| `npm run lint` / `lint:fix` | ESLint (zero warnings enforced) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run test` / `test:watch` / `test:coverage` | Vitest |
| `npm run format` / `format:check` | Prettier |

## Project structure

```
src/
├── assets/       Static images (logo source + derived assets)
├── components/   Shared, reusable UI components
├── features/     Route-level page components (one per screen)
├── hooks/        Reusable React hooks (data fetching, animation helpers)
├── layouts/      App shell — Sidebar, Header, AppLayout
├── lib/          Framework-agnostic library code (chart palette, DTO mappers,
│                 mock data, nav config) — not pure utils, not API calls
├── services/     Backend API client (services/api.ts)
├── stores/       Zustand state stores (auth, theme, UI, toasts, ...)
├── types/        Shared TypeScript types (frontend-facing + raw backend DTOs)
├── utils/        Pure utility/formatting functions (src/utils/index.ts)
├── App.tsx       Route definitions
├── main.tsx      Entry point
└── index.css     Tailwind layers + theme CSS variables
```

## Theming

Three themes (Neon Cyber, Professional Light, Professional Dark) are implemented as
CSS custom properties scoped by `[data-theme]` on `<html>` (see `src/index.css` and
`src/stores/theme.ts`). Tailwind color tokens resolve through those variables via the
`themed()` helper in `tailwind.config.ts`, so switching themes repaints the whole app
without touching component code. Theme selection persists to `localStorage` and falls
back to the OS `prefers-color-scheme` on first visit.

## Testing

Unit tests live in `src/__tests__` and run via Vitest (jsdom environment). There is no
browser/E2E suite in this package — visual verification of UI changes should be done
manually or via a dedicated browser-automation pass outside `npm test`.

## Deployment

This package builds to static assets (`npm run build` → `dist/`) and is deployed as a
static site; see `deployment/` at the repo root for hosting configuration.
