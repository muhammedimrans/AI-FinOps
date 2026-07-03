/**
 * Shared streaming-aggregation helper. Per the ticket: "Support streamed
 * responses. Only send telemetry after the stream completes. Collect
 * final token counts, latency, status." Every provider instrumentor that
 * supports streaming wraps the returned async iterator with this helper
 * rather than reimplementing chunk-buffering logic per provider.
 */

export type OnStreamComplete<T> = (
  chunks: T[],
  elapsedMs: number,
  error: Error | undefined,
) => void | Promise<void>;

/** Wraps an async iterator (or async generator). Chunks are yielded
 * through untouched, immediately — nothing is buffered beyond what the
 * onComplete callback needs for its own aggregation, so streaming
 * latency to the caller is unaffected. */
export async function* instrumentedAsyncStream<T>(
  inner: AsyncIterable<T>,
  start: number,
  onComplete: OnStreamComplete<T>,
): AsyncGenerator<T, void, undefined> {
  const chunks: T[] = [];
  let error: Error | undefined;
  try {
    for await (const chunk of inner) {
      chunks.push(chunk);
      yield chunk;
    }
  } catch (err) {
    error = err instanceof Error ? err : new Error(String(err));
    throw err;
  } finally {
    const elapsedMs = Date.now() - start;
    await onComplete(chunks, elapsedMs, error);
  }
}
