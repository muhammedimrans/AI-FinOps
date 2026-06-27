import type { ApiError } from "@ai-finops/error-codes";
import type { Page } from "@ai-finops/shared-types";

/**
 * Standard success envelope for all API responses (SDD API-6).
 * Discriminated by the `ok` field.
 */
export interface SuccessResponse<T> {
  readonly ok: true;
  readonly data: T;
  readonly requestId: string;
  readonly timestamp: string;
}

/** Standard error envelope. */
export interface ErrorResponse {
  readonly ok: false;
  readonly error: ApiError;
  readonly requestId: string;
  readonly timestamp: string;
}

/** Union of success and error — every endpoint returns this shape. */
export type ApiResponse<T> = SuccessResponse<T> | ErrorResponse;

/** Paginated success response. */
export type PageResponse<T> = SuccessResponse<Page<T>>;
