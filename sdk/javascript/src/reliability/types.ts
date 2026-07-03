/**
 * Shared types for the reliability layer (EP-18.3). One event flows:
 * MemoryQueue -> BackgroundWorker -> PersistentQueue -> Compression ->
 * RetryScheduler -> CircuitBreaker -> ConnectionPool -> Usage API.
 */

import { generateRequestId } from "../util.js";

export interface QueuedEvent {
  payload: Record<string, unknown>;
  eventId: string;
  attempts: number;
}

export function makeQueuedEvent(
  payload: Record<string, unknown>,
  overrides: Partial<Pick<QueuedEvent, "eventId" | "attempts">> = {},
): QueuedEvent {
  return {
    payload,
    eventId: overrides.eventId ?? generateRequestId(),
    attempts: overrides.attempts ?? 0,
  };
}

export type OverflowPolicy = "drop_newest" | "drop_oldest" | "block";

export const OVERFLOW_POLICIES: readonly OverflowPolicy[] = [
  "drop_newest",
  "drop_oldest",
  "block",
];
