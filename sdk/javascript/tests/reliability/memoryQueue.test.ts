import { describe, expect, it } from "vitest";

import { MemoryQueue } from "../../src/reliability/memoryQueue.js";
import { makeQueuedEvent } from "../../src/reliability/types.js";

describe("MemoryQueue", () => {
  it("put and getBatch preserve FIFO order", async () => {
    const q = new MemoryQueue({ maxSize: 10 });
    for (let i = 0; i < 5; i++) {
      expect(await q.put(makeQueuedEvent({ n: i }))).toBe(true);
    }
    const batch = q.getBatch(10);
    expect(batch.map((e) => e.payload.n)).toEqual([0, 1, 2, 3, 4]);
    expect(q.isEmpty()).toBe(true);
  });

  it("getBatch respects maxItems", async () => {
    const q = new MemoryQueue({ maxSize: 10 });
    for (let i = 0; i < 5; i++) await q.put(makeQueuedEvent({ n: i }));
    const batch = q.getBatch(3);
    expect(batch).toHaveLength(3);
    expect(q.size).toBe(2);
  });

  it("drop_newest overflow policy drops the incoming event", async () => {
    const q = new MemoryQueue({ maxSize: 2, overflowPolicy: "drop_newest" });
    expect(await q.put(makeQueuedEvent({ n: 1 }))).toBe(true);
    expect(await q.put(makeQueuedEvent({ n: 2 }))).toBe(true);
    expect(await q.put(makeQueuedEvent({ n: 3 }))).toBe(false);
    expect(q.dropped).toBe(1);
    expect(q.getBatch(10).map((e) => e.payload.n)).toEqual([1, 2]);
  });

  it("drop_oldest overflow policy evicts the oldest event", async () => {
    const q = new MemoryQueue({ maxSize: 2, overflowPolicy: "drop_oldest" });
    await q.put(makeQueuedEvent({ n: 1 }));
    await q.put(makeQueuedEvent({ n: 2 }));
    expect(await q.put(makeQueuedEvent({ n: 3 }))).toBe(true);
    expect(q.dropped).toBe(1);
    expect(q.getBatch(10).map((e) => e.payload.n)).toEqual([2, 3]);
  });

  it("block overflow policy waits for room without dropping", async () => {
    const q = new MemoryQueue({ maxSize: 1, overflowPolicy: "block", blockTimeoutMs: 2000 });
    await q.put(makeQueuedEvent({ n: 1 }));
    setTimeout(() => q.getBatch(1), 50);
    const start = Date.now();
    expect(await q.put(makeQueuedEvent({ n: 2 }))).toBe(true);
    expect(Date.now() - start).toBeLessThan(2000);
  });

  it("block overflow policy times out and drops", async () => {
    const q = new MemoryQueue({ maxSize: 1, overflowPolicy: "block", blockTimeoutMs: 50 });
    await q.put(makeQueuedEvent({ n: 1 }));
    const start = Date.now();
    expect(await q.put(makeQueuedEvent({ n: 2 }))).toBe(false);
    expect(Date.now() - start).toBeGreaterThanOrEqual(45);
    expect(q.dropped).toBe(1);
  });

  it("rejects an invalid maxSize", () => {
    expect(() => new MemoryQueue({ maxSize: 0 })).toThrow();
  });

  it("handles concurrent puts without losing events", async () => {
    const q = new MemoryQueue({ maxSize: 10_000, overflowPolicy: "drop_oldest" });
    await Promise.all(Array.from({ length: 500 }, () => q.put(makeQueuedEvent({ n: 1 }))));
    expect(q.size).toBe(500);
  });
});
