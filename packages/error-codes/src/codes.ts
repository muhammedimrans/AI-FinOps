/**
 * Canonical error codes for the AI FinOps platform.
 *
 * Format: <CATEGORY>_<SPECIFIC>
 * Every code maps 1-to-1 with an HTTP status and a user-facing message.
 * New codes must be added here before use in any service.
 * (SDD API-6: one error model everywhere.)
 */
export const ErrorCode = {
  // ─── Generic ──────────────────────────────────────────────────────────────
  INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
  NOT_IMPLEMENTED: "NOT_IMPLEMENTED",
  SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",

  // ─── Validation ───────────────────────────────────────────────────────────
  VALIDATION_ERROR: "VALIDATION_ERROR",
  INVALID_FIELD: "INVALID_FIELD",
  MISSING_REQUIRED_FIELD: "MISSING_REQUIRED_FIELD",
  INVALID_CURSOR: "INVALID_CURSOR",
  INVALID_DATE_RANGE: "INVALID_DATE_RANGE",
  INVALID_PAGINATION_LIMIT: "INVALID_PAGINATION_LIMIT",

  // ─── Auth ─────────────────────────────────────────────────────────────────
  UNAUTHORIZED: "UNAUTHORIZED",
  FORBIDDEN: "FORBIDDEN",
  TOKEN_EXPIRED: "TOKEN_EXPIRED",
  TOKEN_INVALID: "TOKEN_INVALID",
  API_KEY_INVALID: "API_KEY_INVALID",
  API_KEY_REVOKED: "API_KEY_REVOKED",
  SESSION_EXPIRED: "SESSION_EXPIRED",

  // ─── Not Found ────────────────────────────────────────────────────────────
  ORGANIZATION_NOT_FOUND: "ORGANIZATION_NOT_FOUND",
  PROJECT_NOT_FOUND: "PROJECT_NOT_FOUND",
  USER_NOT_FOUND: "USER_NOT_FOUND",
  BUDGET_NOT_FOUND: "BUDGET_NOT_FOUND",
  ALERT_NOT_FOUND: "ALERT_NOT_FOUND",
  REPORT_NOT_FOUND: "REPORT_NOT_FOUND",
  PROVIDER_CREDENTIAL_NOT_FOUND: "PROVIDER_CREDENTIAL_NOT_FOUND",

  // ─── Conflict ─────────────────────────────────────────────────────────────
  DUPLICATE_IDEMPOTENCY_KEY: "DUPLICATE_IDEMPOTENCY_KEY",
  ORGANIZATION_ALREADY_EXISTS: "ORGANIZATION_ALREADY_EXISTS",
  PROJECT_ALREADY_EXISTS: "PROJECT_ALREADY_EXISTS",
  BUDGET_PERIOD_OVERLAP: "BUDGET_PERIOD_OVERLAP",

  // ─── Rate Limiting ────────────────────────────────────────────────────────
  RATE_LIMIT_EXCEEDED: "RATE_LIMIT_EXCEEDED",
  INGESTION_RATE_LIMIT_EXCEEDED: "INGESTION_RATE_LIMIT_EXCEEDED",

  // ─── Provider ─────────────────────────────────────────────────────────────
  PROVIDER_API_ERROR: "PROVIDER_API_ERROR",
  PROVIDER_AUTH_FAILED: "PROVIDER_AUTH_FAILED",
  PROVIDER_RATE_LIMITED: "PROVIDER_RATE_LIMITED",
  PROVIDER_UNAVAILABLE: "PROVIDER_UNAVAILABLE",
  PROVIDER_UNSUPPORTED: "PROVIDER_UNSUPPORTED",

  // ─── Ingestion ────────────────────────────────────────────────────────────
  INGESTION_SCHEMA_INVALID: "INGESTION_SCHEMA_INVALID",
  INGESTION_BATCH_TOO_LARGE: "INGESTION_BATCH_TOO_LARGE",
} as const;

export type ErrorCode = (typeof ErrorCode)[keyof typeof ErrorCode];
