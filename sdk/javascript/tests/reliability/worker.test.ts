import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { resolveConfig } from "../../src/config.js";
import { ConnectionPool } from "../../src/reliability/connectionPool.js";
import { BackgroundWorker } from "../../src/reliability/worker.js";
import { makeQueuedEvent } from "../../src/reliability/types.js";

const tempDirs: string[] = [];

async function tempPath(name: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "costorah-worker-"));
  tempDirs.push(dir);
  return join(dir, name);
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((d) => rm(d, { recursive: true, force: true })));
});

function successResponse(): Response {
  return new Response(
    JSON.stringify({
      success: true,
      usage_id: "u1",
      request_id: "r1",
      processed_at: "2026-01-01T00:00:00Z",
      duplicate: false,
    }),
    { status: 200 },
  );
}

function makeWorker(
  fetchImpl: typeof fetch,
  options: ConstructorParameters<typeof BackgroundWorker>[1] = {},
): BackgroundWorker {
  const config = resolveConfig({ apiKey: "costorah_live_x", batchSize: 25 });
  const pool = new ConnectionPool(config, fetchImpl);
  const worker = new BackgroundWorker(config, { connectionPool: pool, ...options });
  worker.start();
  return worker;
}

describe("BackgroundWorker — delivery", () => {
  it("delivers events and acks them", async () => {
    let calls = 0;
    const worker = makeWorker(async () => {
      calls += 1;
      return successResponse();
    });
    for (let i = 0; i < 10; i++) {
      await worker.submit(makeQueuedEvent({ provider: "openai", model: "m", request_id: `r${i}` }));
    }
    expect(await worker.flush(5000)).toBe(true);
    expect(calls).toBe(10);
    await worker.shutdown();
  });

  it("drops a permanent (401) failure without retrying", async () => {
    let calls = 0;
    const worker = makeWorker(async () => {
      calls += 1;
      return new Response(JSON.stringify({ detail: "bad key" }), { status: 401 });
    });
    await worker.submit(makeQueuedEvent({ provider: "openai", model: "m", request_id: "r1" }));
    expect(await worker.flush(5000)).toBe(true);
    await worker.shutdown();
    expect(calls).toBe(1);
    expect(worker.metrics.snapshot().failedTotal).toBe(1);
  });

  it("retries a transient (503) failure until success", async () => {
    let remaining = 2;
    const worker = makeWorker(async () => {
      if (remaining > 0) {
        remaining -= 1;
        return new Response(JSON.stringify({ detail: "down" }), { status: 503 });
      }
      return successResponse();
    });
    await worker.submit(makeQueuedEvent({ provider: "openai", model: "m", request_id: "r1" }));
    expect(await worker.flush(10_000)).toBe(true);
    await worker.shutdown();
    expect(remaining).toBe(0);
    expect(worker.metrics.snapshot().sentTotal).toBe(1);
    expect(worker.metrics.snapshot().retryCount).toBe(2);
  }, 15_000);

  it("retryEnabled: false drops on the first transient failure", async () => {
    let calls = 0;
    const worker = makeWorker(
      async () => {
        calls += 1;
        return new Response(JSON.stringify({ detail: "down" }), { status: 503 });
      },
      { retryEnabled: false },
    );
    await worker.submit(makeQueuedEvent({ provider: "openai", model: "m", request_id: "r1" }));
    expect(await worker.flush(5000)).toBe(true);
    await worker.shutdown();
    expect(calls).toBe(1);
  });
});

describe("BackgroundWorker — overflow", () => {
  it("drop_newest overflow drops the incoming event", async () => {
    const worker = makeWorker(async () => successResponse(), {
      queueSize: 1,
      overflowPolicy: "drop_newest",
      pollIntervalMs: 5000, // keep the worker from draining during the test
    });
    expect(await worker.submit(makeQueuedEvent({ n: 1 }))).toBe(true);
    expect(await worker.submit(makeQueuedEvent({ n: 2 }))).toBe(false);
    expect(worker.memoryQueue.dropped).toBe(1);
  });
});

describe("BackgroundWorker — crash recovery", () => {
  it("survives being reopened at the same persistent queue path", async () => {
    const path = await tempPath("queue.jsonl");

    const worker1 = makeWorker(async () => new Response(JSON.stringify({ detail: "down" }), { status: 503 }), {
      persistentQueuePath: path,
    });
    await worker1.submit(
      makeQueuedEvent({ provider: "openai", model: "m", request_id: "r1" }, { eventId: "crash-1" }),
    );
    // Give it a pass to persist the event, then simulate a crash — no
    // graceful shutdown/flush.
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(worker1.persistentQueue.count()).toBe(1);
    await worker1.persistentQueue.close();

    const worker2 = makeWorker(async () => successResponse(), { persistentQueuePath: path });
    expect(await worker2.flush(5000)).toBe(true);
    await worker2.shutdown();
  });
});

describe("BackgroundWorker — compression", () => {
  it("sets Content-Encoding: gzip for a large payload", async () => {
    const headersSeen: Headers[] = [];
    const worker = makeWorker(async (_url, init) => {
      headersSeen.push(new Headers(init?.headers));
      return successResponse();
    });
    await worker.submit(
      makeQueuedEvent({
        provider: "openai",
        model: "m",
        request_id: "r1",
        metadata: { blob: "x".repeat(5000) },
      }),
    );
    expect(await worker.flush(5000)).toBe(true);
    await worker.shutdown();
    expect(headersSeen[0]?.get("content-encoding")).toBe("gzip");
    expect(worker.metrics.snapshot().compressionRatio).not.toBeNull();
  });

  it("compressionEnabled: false never sets Content-Encoding", async () => {
    const headersSeen: Headers[] = [];
    const worker = makeWorker(
      async (_url, init) => {
        headersSeen.push(new Headers(init?.headers));
        return successResponse();
      },
      { compressionEnabled: false },
    );
    await worker.submit(
      makeQueuedEvent({
        provider: "openai",
        model: "m",
        request_id: "r1",
        metadata: { blob: "x".repeat(5000) },
      }),
    );
    expect(await worker.flush(5000)).toBe(true);
    await worker.shutdown();
    expect(headersSeen[0]?.has("content-encoding")).toBe(false);
  });
});

describe("BackgroundWorker — concurrency", () => {
  it("handles many concurrent submits", async () => {
    let calls = 0;
    const worker = makeWorker(async () => {
      calls += 1;
      return successResponse();
    });
    await Promise.all(
      Array.from({ length: 200 }, (_, i) =>
        worker.submit(makeQueuedEvent({ provider: "openai", model: "m", request_id: `r${i}` })),
      ),
    );
    expect(await worker.flush(15_000)).toBe(true);
    await worker.shutdown();
    expect(calls).toBe(200);
  }, 20_000);
});
