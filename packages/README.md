# packages/

TypeScript packages shared across the AI FinOps monorepo.

Managed with pnpm workspaces. All packages are private (not published to npm).

## In-Scope Packages (EP-01)

| Package | Version | Description |
|---|---|---|
| [`@ai-finops/shared-types`](./shared-types/) | 0.1.0 | Branded IDs, enums, pagination, monetary types |
| [`@ai-finops/error-codes`](./error-codes/) | 0.1.0 | Canonical error catalog and API error envelope |
| [`@ai-finops/event-schema`](./event-schema/) | 0.1.0 | Usage event schema for ingestion and analytics |
| [`@ai-finops/shared-config`](./shared-config/) | 0.1.0 | Configuration types, feature flags, platform limits |
| [`@ai-finops/api-contracts`](./api-contracts/) | 0.1.0 | REST API request/response types |

## Out-of-Scope Packages (future sprints)

| Package | Description |
|---|---|
| [`pricing-engine`](./pricing-engine/) | Token pricing calculations and model price catalog |
| [`ui-components`](./ui-components/) | Shared React component library |

## Dependency Graph

```
shared-types    (no deps)
error-codes     (no deps)
shared-config  → shared-types
event-schema   → shared-types
api-contracts  → shared-types, error-codes, event-schema
```

## Building

```bash
# Build all packages
pnpm --filter "./packages/*" build

# Build a single package
pnpm --filter @ai-finops/shared-types build

# Type-check all packages
pnpm --filter "./packages/*" typecheck
```

## Adding a New Package

1. Create the directory under `packages/`
2. Add `package.json` with `@ai-finops/<name>` as the name
3. Add `tsconfig.json` extending `../../tsconfig.base.json`
4. Add a reference to `tsconfig.json` in the root `tsconfig.json`
5. Add to the workspace references if another package depends on it
