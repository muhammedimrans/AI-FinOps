/**
 * RetryScheduler — exponential backoff with the ticket's exact default
 * schedule. Retries forever (no max-attempt cutoff) for transient
 * failures, matching the "at-least-once, never exactly-once" delivery
 * guarantee — an event is only ever removed from the queue by successful
 * delivery, a permanent rejection (see `isRetryable`), or overflow
 * eviction.
 */

export const DEFAULT_BACKOFF_SECONDS: readonly number[] = [1, 2, 4, 8, 16, 30, 60, 120, 300];

const NEVER_RETRY = new Set([400, 401, 403, 404]);
const RETRYABLE = new Set([408, 429, 500, 502, 503, 504]);

/** True for transient failures (network errors with no status code) and
 * the ticket's explicit retryable status list. False for permanent
 * client errors — retrying an unchanged payload against those can never
 * succeed. */
export function isRetryable(statusCode: number | undefined): boolean {
  if (statusCode === undefined) return true;
  if (NEVER_RETRY.has(statusCode)) return false;
  if (RETRYABLE.has(statusCode)) return true;
  return statusCode >= 500;
}

export class RetryScheduler {
  private readonly schedule: readonly number[];

  constructor(schedule: readonly number[] = DEFAULT_BACKOFF_SECONDS) {
    if (schedule.length === 0) throw new Error("schedule must not be empty");
    this.schedule = schedule;
  }

  /** attempt is 1-indexed: the delay before retry #1 is nextDelay(1). */
  nextDelaySeconds(attempt: number): number {
    const index = Math.min(Math.max(attempt, 1) - 1, this.schedule.length - 1);
    return this.schedule[index]!;
  }
}
