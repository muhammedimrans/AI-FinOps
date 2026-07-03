import { describe, expect, it } from "vitest";

import { instrumentedAsyncStream } from "../../src/instrumentation/streaming.js";

async function* asyncGen<T>(items: T[]): AsyncGenerator<T, void, undefined> {
  for (const item of items) yield item;
}

async function* asyncGenThatThrows<T>(items: T[], err: Error): AsyncGenerator<T, void, undefined> {
  for (const item of items) yield item;
  throw err;
}

describe("instrumentedAsyncStream", () => {
  it("yields every chunk through untouched", async () => {
    const out: number[] = [];
    for await (const chunk of instrumentedAsyncStream(asyncGen([1, 2, 3]), Date.now(), () => {})) {
      out.push(chunk);
    }
    expect(out).toEqual([1, 2, 3]);
  });

  it("calls onComplete exactly once after full consumption, with no error", async () => {
    let calls = 0;
    let capturedChunks: number[] = [];
    let capturedError: Error | undefined;
    for await (const chunk of instrumentedAsyncStream(asyncGen([1, 2, 3]), Date.now(), (chunks, _ms, error) => {
      calls += 1;
      capturedChunks = chunks;
      capturedError = error;
    })) {
      void chunk;
    }
    expect(calls).toBe(1);
    expect(capturedChunks).toEqual([1, 2, 3]);
    expect(capturedError).toBeUndefined();
  });

  it("calls onComplete with the error and partial chunks on failure, and re-throws", async () => {
    const boom = new Error("stream broke");
    let capturedError: Error | undefined;
    let capturedChunks: number[] = [];
    const consume = async () => {
      for await (const chunk of instrumentedAsyncStream(
        asyncGenThatThrows([1, 2], boom),
        Date.now(),
        (chunks, _ms, error) => {
          capturedChunks = chunks;
          capturedError = error;
        },
      )) {
        void chunk;
      }
    };
    await expect(consume()).rejects.toThrow("stream broke");
    expect(capturedChunks).toEqual([1, 2]);
    expect(capturedError).toBe(boom);
  });

  it("reports elapsed time based on the given start", async () => {
    let elapsed = -1;
    const start = Date.now() - 50;
    for await (const chunk of instrumentedAsyncStream(asyncGen([1]), start, (_chunks, ms) => {
      elapsed = ms;
    })) {
      void chunk;
    }
    expect(elapsed).toBeGreaterThanOrEqual(50);
  });

  it("handles an empty stream", async () => {
    let calls = 0;
    let capturedChunks: number[] | undefined;
    for await (const chunk of instrumentedAsyncStream(asyncGen<number>([]), Date.now(), (chunks) => {
      calls += 1;
      capturedChunks = chunks;
    })) {
      void chunk;
    }
    expect(calls).toBe(1);
    expect(capturedChunks).toEqual([]);
  });
});
