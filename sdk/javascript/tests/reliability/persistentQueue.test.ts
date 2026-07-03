import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { PersistentQueue } from "../../src/reliability/persistentQueue.js";
import { makeQueuedEvent } from "../../src/reliability/types.js";

const tempDirs: string[] = [];

async function tempPath(name: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "costorah-pq-"));
  tempDirs.push(dir);
  return join(dir, name);
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((d) => rm(d, { recursive: true, force: true })));
});

describe("PersistentQueue — ephemeral (no path)", () => {
  it("enqueue and dequeueDue works without any file I/O", async () => {
    const q = new PersistentQueue();
    await q.whenReady();
    q.enqueue(makeQueuedEvent({ n: 1 }, { eventId: "e1" }));
    const due = q.dequeueDue(10);
    expect(due).toHaveLength(1);
    expect(due[0]!.eventId).toBe("e1");
  });

  it("markRetry delays future dequeue", async () => {
    const q = new PersistentQueue();
    await q.whenReady();
    q.enqueue(makeQueuedEvent({}, { eventId: "e1" }));
    q.markRetry("e1", 1, Date.now() + 60_000);
    expect(q.dequeueDue(10)).toHaveLength(0);
    expect(q.count()).toBe(1);
  });

  it("ack removes the event", async () => {
    const q = new PersistentQueue();
    await q.whenReady();
    q.enqueue(makeQueuedEvent({}, { eventId: "e1" }));
    expect(q.count()).toBe(1);
    q.ack("e1");
    expect(q.count()).toBe(0);
  });

  it("dequeueDue orders by creation time", async () => {
    const q = new PersistentQueue();
    await q.whenReady();
    for (let i = 0; i < 5; i++) {
      q.enqueue(makeQueuedEvent({ n: i }, { eventId: `e${i}` }));
    }
    const due = q.dequeueDue(5);
    expect(due.map((e) => e.eventId)).toEqual(["e0", "e1", "e2", "e3", "e4"]);
  });
});

describe("PersistentQueue — durable file", () => {
  it("survives being reopened at the same path (simulated restart)", async () => {
    const path = await tempPath("queue.jsonl");
    const q1 = new PersistentQueue(path);
    await q1.whenReady();
    q1.enqueue(makeQueuedEvent({ n: 1 }, { eventId: "e1" }));
    await q1.close();

    const q2 = new PersistentQueue(path);
    await q2.whenReady();
    const due = q2.dequeueDue(10);
    expect(due).toHaveLength(1);
    expect(due[0]!.eventId).toBe("e1");
    await q2.close();
  });

  it("does not durably persist an acked event", async () => {
    const path = await tempPath("queue.jsonl");
    const q1 = new PersistentQueue(path);
    await q1.whenReady();
    q1.enqueue(makeQueuedEvent({}, { eventId: "e1" }));
    q1.ack("e1");
    await q1.close();

    const q2 = new PersistentQueue(path);
    await q2.whenReady();
    expect(q2.count()).toBe(0);
    await q2.close();
  });

  it("survives a missing/never-created file gracefully", async () => {
    const path = await tempPath("does-not-exist.jsonl");
    const q = new PersistentQueue(path);
    await q.whenReady();
    expect(q.count()).toBe(0);
    await q.close();
  });

  it("skips a corrupt trailing line without losing prior entries", async () => {
    const path = await tempPath("queue.jsonl");
    const q1 = new PersistentQueue(path);
    await q1.whenReady();
    q1.enqueue(makeQueuedEvent({ n: 1 }, { eventId: "e1" }));
    await q1.close();

    // Simulate a crash mid-write: append a truncated JSON line.
    const { appendFile } = await import("node:fs/promises");
    await appendFile(path, '{"op":"put","id":"e2","row":{incomple');

    const q2 = new PersistentQueue(path);
    await q2.whenReady();
    expect(q2.count()).toBe(1);
    const due = q2.dequeueDue(10);
    expect(due[0]!.eventId).toBe("e1");
    await q2.close();
  });

  it("compacts the log file after many operations", async () => {
    const path = await tempPath("queue.jsonl");
    const q = new PersistentQueue(path);
    await q.whenReady();
    for (let i = 0; i < 600; i++) {
      const id = `e${i}`;
      q.enqueue(makeQueuedEvent({ n: i }, { eventId: id }));
      q.ack(id);
    }
    await q.close();

    // Compaction (every 500 ops) rewrites the log to only live rows —
    // with all 600 pairs acked, the file must be smaller than the 1200
    // raw put+ack log lines that were actually appended, proving at
    // least one compaction pass ran instead of the log growing
    // unboundedly forever.
    const content = await readFile(path, "utf-8");
    const lineCount = content.split("\n").filter((l) => l.trim()).length;
    expect(lineCount).toBeLessThan(1200);
  });
});
