import type { UsageEventInput } from "./usage-event.js";

/** Maximum events per batch ingestion call (SDD §5 ingestion rate limits). */
export const MAX_BATCH_SIZE = 1000 as const;

/** Batch ingestion envelope — wraps multiple events in a single push. */
export interface UsageEventBatch {
  readonly events: readonly UsageEventInput[];
}

/** Result of a batch ingestion call. */
export interface UsageEventBatchResult {
  readonly accepted: number;
  readonly rejected: number;
  readonly rejectedIndexes: readonly number[];
}
