# @ai-finops/shared-config

Shared configuration types, constants, and defaults for the AI FinOps platform. Consumed by both the frontend and backend services.

## Purpose

Centralise configuration shapes and operational limits so they are defined once and enforced consistently across every service. The backend reads config from environment variables; the frontend reads from Vite env vars; both types are validated against the interfaces here.

## Responsibilities

- **`AppConfig`** — top-level configuration interface with environment, log level, currency, API base URL, and version.
- **`DEFAULT_APP_CONFIG`** — safe defaults for local development.
- **`FeatureFlag`** — canonical feature flag keys; prevents string literals scattered across the codebase.
- **`FeatureFlags`** / **`DEFAULT_FEATURE_FLAGS`** — all flags default to `false` in a fresh deployment.
- **`PLATFORM_LIMITS`** — operator-configurable operational limits (batch sizes, pagination, rate limits). Single source of truth — validated in the backend, displayed in the frontend.

## Package Structure

```
src/
├── index.ts         # re-exports
├── app-config.ts    # AppConfig interface + defaults
├── feature-flags.ts # FeatureFlag keys + defaults
└── limits.ts        # PLATFORM_LIMITS constants
```

## Dependencies

- `@ai-finops/shared-types` — `Currency` enum.

## Usage

```typescript
import { PLATFORM_LIMITS, FeatureFlag, DEFAULT_FEATURE_FLAGS } from "@ai-finops/shared-config";

// Use limit constants instead of magic numbers
if (events.length > PLATFORM_LIMITS.MAX_INGESTION_BATCH_SIZE) {
  throw new Error("Batch too large");
}
```

## Versioning

Constants are stable. Changing a limit value is a minor bump; removing a constant is a major bump.

## Future Implementation

- Runtime config loading from a configuration service (Consul, etcd, or environment).
- Per-tenant overrides for `PLATFORM_LIMITS`.
- Type-safe env var parsing utilities.
