/** Branded nominal type helper — prevents accidental mixing of same-shape IDs. */
export type Brand<T, B extends string> = T & { readonly __brand: B };

/** Opaque UUID string types. */
export type OrganizationId = Brand<string, "OrganizationId">;
export type ProjectId = Brand<string, "ProjectId">;
export type UserId = Brand<string, "UserId">;
export type ApiKeyId = Brand<string, "ApiKeyId">;
export type UsageEventId = Brand<string, "UsageEventId">;
export type BudgetId = Brand<string, "BudgetId">;
export type AlertId = Brand<string, "AlertId">;
export type ReportId = Brand<string, "ReportId">;
export type IdempotencyKey = Brand<string, "IdempotencyKey">;

/** ISO 8601 timestamp string — always UTC. */
export type ISOTimestamp = Brand<string, "ISOTimestamp">;

/** Semantic version string, e.g. "1.0.0". */
export type SemVer = Brand<string, "SemVer">;

/** Cursor token for pagination (opaque, base64-encoded). */
export type Cursor = Brand<string, "Cursor">;

/** Bare UUID without branding, for interop. */
export type UUID = string;

/** Constructor helpers — narrow raw strings to branded types. */
export const asOrganizationId = (v: string): OrganizationId => v as OrganizationId;
export const asProjectId = (v: string): ProjectId => v as ProjectId;
export const asUserId = (v: string): UserId => v as UserId;
export const asUsageEventId = (v: string): UsageEventId => v as UsageEventId;
export const asBudgetId = (v: string): BudgetId => v as BudgetId;
export const asIdempotencyKey = (v: string): IdempotencyKey => v as IdempotencyKey;
