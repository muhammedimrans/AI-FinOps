# @costorah/shared-ui

Shared design-system layer for `apps/website` and `apps/dashboard`.

## Current contents

- `cn()` — class-name merge utility (clsx + tailwind-merge), previously duplicated verbatim in both apps.

## Planned (EP-26 — Design system unification, see `/CLAUDE.md`)

- shadcn/ui primitives seeded from `apps/website/src/components/ui/` (already installed there, unused), adopted incrementally by `apps/dashboard` in place of its hand-rolled equivalents (`Dialog`, `Popover`, `Avatar`, `ConfirmDialog`, `ToastContainer`).
- Shared design tokens (fonts, brand color, radius scale) as CSS custom properties, reconciling the OKLCH/RGB-triplet and dark-only/3-theme differences documented in `CLAUDE.md` §5.
- `PROVIDER_COLORS` (currently hardcoded in `apps/dashboard/src/lib/providerCatalog.ts`) moves to `packages/shared-utils` per the merge plan, not here — this package is presentation primitives, not domain constants.
