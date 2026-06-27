# @ai-finops/error-codes

Canonical error code catalog for the AI FinOps platform. Every API error response across every service uses the codes and types defined here.

## Purpose

Implements SDD API-6: _"One error model everywhere."_ Consumers (frontend, SDK, integration tests) import error codes by name rather than matching raw strings, so a rename is caught at compile time.

## Responsibilities

- **`ErrorCategory`** — top-level taxonomy (AUTH, NOT_FOUND, RATE_LIMIT, SERVER, PROVIDER, VALIDATION, …) mapping to HTTP status classes.
- **`ErrorCode`** — exhaustive set of `const` string literals for every failure mode in the platform.
- **`ApiError`** / **`ValidationError`** — the canonical response envelope shape. All services return this and only this on failure.
- **`HTTP_STATUS`** — maps `ErrorCategory` to HTTP status codes; authoritative for the API layer.

## Package Structure

```
src/
├── index.ts       # re-exports
├── categories.ts  # ErrorCategory enum
├── codes.ts       # ErrorCode const object + type
└── types.ts       # ApiError, FieldError, ValidationError, HTTP_STATUS
```

## Dependencies

None. Zero runtime dependencies.

## Usage

```typescript
import { ErrorCode, ErrorCategory, ApiError, HTTP_STATUS } from "@ai-finops/error-codes";

const error: ApiError = {
  code: ErrorCode.ORGANIZATION_NOT_FOUND,
  category: ErrorCategory.NotFound,
  message: "Organization not found.",
  requestId: req.id,
};
```

## Versioning

Adding new error codes is backward-compatible. Removing or renaming a code is a breaking change requiring a major version bump.

## Future Implementation

- Machine-readable error catalog with default HTTP status, user-facing message template, and retry guidance per code.
- Localized message strings (i18n).
