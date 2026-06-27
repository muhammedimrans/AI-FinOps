import type { Cursor } from "./primitives.js";

/** Cursor-based pagination parameters (SDD §4.8, API principle API-7). */
export interface PaginationParams {
  readonly cursor?: Cursor;
  readonly limit?: number;
}

/** Pagination metadata returned with every list response. */
export interface PageInfo {
  readonly hasNextPage: boolean;
  readonly hasPreviousPage: boolean;
  readonly startCursor: Cursor | null;
  readonly endCursor: Cursor | null;
  readonly totalCount?: number;
}

/** Generic paginated list envelope. */
export interface Page<T> {
  readonly data: readonly T[];
  readonly pageInfo: PageInfo;
}

/** Sort direction. */
export type SortDirection = "asc" | "desc";

/** Generic sort parameter. */
export interface SortParam<T extends string = string> {
  readonly field: T;
  readonly direction: SortDirection;
}
