/**
 * MemoryQueue — the fast, in-process buffer `track()` writes into.
 * `put()` never performs I/O; for `overflowPolicy: "block"` it returns a
 * promise that resolves once room frees up (bounded by `blockTimeoutMs`)
 * rather than truly blocking Node's single-threaded event loop — other
 * work keeps running while it waits, matching how `track()` is already
 * async in this SDK.
 */

import type { OverflowPolicy, QueuedEvent } from "./types.js";

export interface MemoryQueueOptions {
  maxSize?: number;
  overflowPolicy?: OverflowPolicy;
  blockTimeoutMs?: number;
}

export class MemoryQueue {
  private readonly maxSize: number;
  private readonly overflowPolicy: OverflowPolicy;
  private readonly blockTimeoutMs: number;
  private items: QueuedEvent[] = [];
  private droppedCount = 0;
  private waiters: (() => void)[] = [];

  constructor(options: MemoryQueueOptions = {}) {
    this.maxSize = options.maxSize ?? 10_000;
    this.overflowPolicy = options.overflowPolicy ?? "drop_oldest";
    this.blockTimeoutMs = options.blockTimeoutMs ?? 1000;
    if (this.maxSize <= 0) throw new Error("maxSize must be positive");
  }

  /** Resolves True if the event was queued, False if dropped. */
  async put(event: QueuedEvent): Promise<boolean> {
    if (this.items.length < this.maxSize) {
      this.items.push(event);
      return true;
    }

    if (this.overflowPolicy === "drop_newest") {
      this.droppedCount += 1;
      return false;
    }

    if (this.overflowPolicy === "drop_oldest") {
      this.items.shift();
      this.items.push(event);
      this.droppedCount += 1;
      return true;
    }

    // block: wait for room, bounded by blockTimeoutMs.
    const gotRoom = await this.waitForRoom(this.blockTimeoutMs);
    if (!gotRoom) {
      this.droppedCount += 1;
      return false;
    }
    this.items.push(event);
    return true;
  }

  private waitForRoom(timeoutMs: number): Promise<boolean> {
    if (this.items.length < this.maxSize) return Promise.resolve(true);
    return new Promise((resolve) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (settled) return;
        settled = true;
        resolve(false);
      }, timeoutMs);
      this.waiters.push(() => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(true);
      });
    });
  }

  private notifyRoom(): void {
    if (this.items.length >= this.maxSize) return;
    const waiter = this.waiters.shift();
    if (waiter) waiter();
  }

  getBatch(maxItems: number): QueuedEvent[] {
    const batch = this.items.splice(0, maxItems);
    if (batch.length > 0) this.notifyRoom();
    return batch;
  }

  get size(): number {
    return this.items.length;
  }

  get dropped(): number {
    return this.droppedCount;
  }

  isEmpty(): boolean {
    return this.items.length === 0;
  }
}
