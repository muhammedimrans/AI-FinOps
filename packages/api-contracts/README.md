# @ai-finops/api-contracts

API request/response type contracts for the AI FinOps platform. The TypeScript representation of the REST API surface defined in SDD Chapter 5.

## Purpose

Ensures the frontend, SDKs, and integration tests all share a single definition of every request body and response shape. When the API contract changes, updating this package propagates type errors to every consumer at compile time.

## Responsibilities

- **`ApiResponse<T>`** / **`ErrorResponse`** — the standard success/error envelope (SDD API-6).
- **`PageResponse<T>`** — paginated list envelope wrapping `Page<T>`.
- **Health contracts** — `HealthResponse`, `ReadyResponse`, `MetricsResponse` for `/health`, `/ready`, `/metrics`.
- **Ingestion contracts** — `IngestEventRequest`, `IngestBatchRequest` and their response types for the event push API.
- **Resource contracts** — `Organization`, `Project` with their `Create*` and `Update*` request bodies.

## Package Structure

```
src/
├── index.ts          # re-exports
├── envelope.ts       # ApiResponse, SuccessResponse, ErrorResponse, PageResponse
├── health.ts         # HealthResponse, ReadyResponse, MetricsResponse
├── ingestion.ts      # IngestEventRequest, IngestBatchRequest, responses
├── organizations.ts  # Organization resource + mutations
└── projects.ts       # Project resource + mutations
```

## Dependencies

- `@ai-finops/shared-types` — branded IDs, pagination, enums.
- `@ai-finops/error-codes` — `ApiError` shape.
- `@ai-finops/event-schema` — `UsageEventInput` for ingestion contracts.

## Usage

```typescript
import type { ApiResponse, HealthResponse, IngestBatchRequest } from "@ai-finops/api-contracts";

// Type-safe fetch wrapper
async function fetchHealth(): Promise<ApiResponse<HealthResponse>> {
  const res = await fetch("/health");
  return res.json() as Promise<ApiResponse<HealthResponse>>;
}
```

## Versioning

This package tracks the API version. A v2 API surface would live in `src/v2/`. Breaking changes to existing types require a package major version bump.

## Future Implementation

- Generated from the OpenAPI spec (single-direction: spec → types).
- Zod schemas co-located with each contract for runtime validation.
- gRPC/protobuf contracts for internal service communication.
- Webhook event payload types.
