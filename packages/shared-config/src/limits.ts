/** Platform-wide operational limits. All values are defaults; operators may override. */
export const PLATFORM_LIMITS = {
  /** Maximum events per batch ingestion request. */
  MAX_INGESTION_BATCH_SIZE: 1000,

  /** Maximum labels per usage event. */
  MAX_EVENT_LABELS: 20,

  /** Maximum label key length in bytes. */
  MAX_LABEL_KEY_BYTES: 64,

  /** Maximum label value length in bytes. */
  MAX_LABEL_VALUE_BYTES: 256,

  /** Maximum cursor-based pagination page size. */
  MAX_PAGE_SIZE: 500,

  /** Default page size. */
  DEFAULT_PAGE_SIZE: 50,

  /** Maximum date range for analytics queries in days. */
  MAX_QUERY_RANGE_DAYS: 366,

  /** Maximum number of projects per organization (soft limit). */
  MAX_PROJECTS_PER_ORG: 100,

  /** Maximum number of budgets per project. */
  MAX_BUDGETS_PER_PROJECT: 10,

  /** Maximum number of alert rules per budget. */
  MAX_ALERTS_PER_BUDGET: 10,

  /** Default rate limit: requests per minute per API key. */
  DEFAULT_API_RATE_LIMIT_RPM: 1000,

  /** Default ingestion rate: events per minute per organization. */
  DEFAULT_INGESTION_RATE_LIMIT_EPM: 100_000,
} as const;

export type PlatformLimits = typeof PLATFORM_LIMITS;
