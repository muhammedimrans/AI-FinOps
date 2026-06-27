# @ai-finops/shared-types

Shared TypeScript types for the AI FinOps platform. The single source of truth for primitive types, branded IDs, enumerations, pagination, and monetary representations used across frontend, packages, and future SDKs.

## Purpose

Centralise the types that appear in more than one package. Avoids duplication and ensures that `Provider.OpenAI` in the frontend is the same literal as in `event-schema` or `api-contracts`.

## Responsibilities

- **Branded nominal types** — `OrganizationId`, `ProjectId`, `UsageEventId`, etc. Prevents passing a raw `string` where a typed ID is expected.
- **Enumerations** — `Provider`, `TokenType`, `Modality`, `Currency`, `TimeGranularity`, `Status`, `BudgetPeriod`, `ReconciliationState`.
- **Pagination** — `PaginationParams`, `PageInfo`, `Page<T>` — implements the cursor-based pagination contract (SDD API-7).
- **Monetary types** — `Money`, `TokenCost`, `TokenUsage` — integer micro-USD arithmetic to prevent float drift.

## Package Structure

```
src/
├── index.ts        # re-exports everything
├── primitives.ts   # branded ID types and constructors
├── enums.ts        # all platform enumerations
├── pagination.ts   # cursor pagination types
└── money.ts        # monetary and token-cost types
```

## Dependencies

None. This package must have zero runtime dependencies so it can be imported by any consumer.

## Usage

```typescript
import { Provider, OrganizationId, Page, Money } from "@ai-finops/shared-types";
```

## Versioning

Follows the repository's versioning strategy. Breaking changes (removing or renaming exports) require a major version bump and must be announced in the changelog. Additive changes (new enums, new fields) are backward-compatible.

## Future Implementation

As the platform grows this package will receive:
- Additional provider enums
- Extended token/cost types for image and audio modalities
- Locale and timezone types for multi-region support
