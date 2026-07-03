/** Small internal helpers. */

/** A globally unique request_id for callers who don't supply their own.
 * Uses randomness rather than a content hash, since manual track() calls
 * have no natural dedup key the way a provider response's own request ID
 * does (that's EP-18.2's automatic instrumentation territory). */
export function generateRequestId(): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  return `sdk_js_${random}`;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
