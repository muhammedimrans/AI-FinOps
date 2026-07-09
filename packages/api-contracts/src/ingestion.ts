import type { UsageEventInput } from "@costorah/event-schema";
import type { UsageEventBatchResult } from "@costorah/event-schema";

/** POST /v1/ingest/events — single event. */
export interface IngestEventRequest {
  readonly event: UsageEventInput;
}

/** POST /v1/ingest/events — single event response. */
export interface IngestEventResponse {
  readonly eventId: string;
  readonly accepted: true;
}

/** POST /v1/ingest/events/batch — batch event ingestion. */
export interface IngestBatchRequest {
  readonly events: readonly UsageEventInput[];
}

/** POST /v1/ingest/events/batch — batch response. */
export type IngestBatchResponse = UsageEventBatchResult;
