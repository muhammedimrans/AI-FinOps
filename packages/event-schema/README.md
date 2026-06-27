# @ai-finops/event-schema

Usage event schemas for the AI FinOps platform. Defines the shape of every AI usage event that flows through the ingestion pipeline — from SDK push to provider reconciliation.

## Purpose

The `UsageEvent` is the atomic unit of cost tracking. Everything downstream (cost attribution, budgets, forecasting, reports) is derived from this schema. Centralising it here ensures the SDK, the collector API, the processing workers, and the frontend all work from an identical contract.

## Responsibilities

- **`UsageEvent`** — the fully-hydrated event stored in ClickHouse after processing.
- **`UsageEventInput`** — the input shape accepted by the ingestion API (no cost fields — the platform calculates cost server-side from the pricing catalog).
- **`UsageEventBatch`** — the batch ingestion envelope (up to `MAX_BATCH_SIZE` events per request).
- **`EVENT_SCHEMA_VERSION`** — semver constant embedded in every event to allow forward-compatible schema evolution.

## Package Structure

```
src/
├── index.ts          # re-exports
├── schema-version.ts # version constant
├── usage-event.ts    # UsageEvent + UsageEventInput
└── batch.ts          # UsageEventBatch + MAX_BATCH_SIZE
```

## Dependencies

- `@ai-finops/shared-types` — Provider, Modality, TokenUsage, branded ID types.

## Usage

```typescript
import { UsageEventInput, UsageEventBatch, EVENT_SCHEMA_VERSION } from "@ai-finops/event-schema";
import { Provider, Modality } from "@ai-finops/shared-types";

const event: UsageEventInput = {
  schemaVersion: EVENT_SCHEMA_VERSION,
  organizationId: asOrganizationId("org-123"),
  projectId: asProjectId("proj-456"),
  provider: Provider.OpenAI,
  model: "gpt-4o-2024-08-06",
  modality: Modality.Text,
  requestedAt: "2026-06-27T10:00:00.000Z" as ISOTimestamp,
  tokenUsage: { inputTokens: 100, outputTokens: 50, cachedInputTokens: 0, totalTokens: 150 },
};
```

## Versioning

`EVENT_SCHEMA_VERSION` is embedded in every event at ingestion time. When a field is added, bump the minor version. When a field is removed or renamed, bump the major version and provide a migration for historical data.

## Future Implementation

- JSON Schema / Zod validation at the ingestion boundary.
- Schema registry integration for evolution governance.
- Streaming event types (for providers that return partial token counts mid-stream).
