import type { ErrorCategory } from "./categories.js";
import type { ErrorCode } from "./codes.js";

/**
 * Standard error envelope — every API error response uses this shape.
 * (SDD API-6: one error model everywhere.)
 */
export interface ApiError {
  readonly code: ErrorCode;
  readonly category: ErrorCategory;
  readonly message: string;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;
}

/** Field-level validation error detail. */
export interface FieldError {
  readonly field: string;
  readonly code: ErrorCode;
  readonly message: string;
}

/** Validation error with per-field breakdown. */
export interface ValidationError extends ApiError {
  readonly code: "VALIDATION_ERROR";
  readonly fields: readonly FieldError[];
}

/** HTTP status code mapped to error category. */
export const HTTP_STATUS: Record<ErrorCategory, number> = {
  CLIENT: 400,
  AUTH: 401,
  NOT_FOUND: 404,
  CONFLICT: 409,
  RATE_LIMIT: 429,
  VALIDATION: 422,
  SERVER: 500,
  PROVIDER: 502,
} as const;
