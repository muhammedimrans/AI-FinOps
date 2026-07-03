/**
 * PersistentQueue — durability checkpoint so telemetry survives a
 * process crash/restart, per the ticket's "When process crashes -> Queue
 * survives restart" requirement.
 *
 * The ticket suggests "LevelDB or equivalent lightweight embedded
 * storage." This SDK ships with **zero runtime dependencies** (see
 * `README.md`'s Requirements section) — adding LevelDB (or any other
 * embedded-DB package) would break that guarantee for every consumer,
 * not just those who opt into `persistentQueue: true`. Instead this
 * implements the same durability property (crash-safe, replay-on-restart)
 * with a plain newline-delimited JSON append log via Node's built-in
 * `fs/promises` — genuinely "equivalent lightweight embedded storage,"
 * just without a binary dependency: an in-memory Map is the fast path for
 * every operation, mirrored to an append-only log file for durability,
 * with periodic compaction so the log doesn't grow unboundedly. On
 * construction, an existing log is replayed to rebuild state exactly as
 * SQLite's WAL replay does for the Python SDK.
 *
 * `path: undefined` (the default, used when `persistentQueue: false`)
 * skips all file I/O — the same queue/retry mechanics, just not durable
 * across a restart, mirroring the Python SDK's `:memory:` mode.
 */

import { appendFile, mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import type { QueuedEvent } from "./types.js";

interface Row {
  payload: Record<string, unknown>;
  attempts: number;
  createdAt: number;
  nextRetryAt: number;
}

type LogLine =
  | { op: "put"; id: string; row: Row }
  | { op: "retry"; id: string; attempts: number; nextRetryAt: number }
  | { op: "ack"; id: string };

export class PersistentQueue {
  private readonly path: string | undefined;
  private rows = new Map<string, Row>();
  private ready: Promise<void>;
  private writeQueue: Promise<void> = Promise.resolve();
  private opsSinceCompaction = 0;
  private closed = false;

  constructor(path?: string) {
    this.path = path;
    this.ready = path ? this.replay(path) : Promise.resolve();
  }

  private async replay(path: string): Promise<void> {
    await mkdir(dirname(path), { recursive: true });
    let content: string;
    try {
      content = await readFile(path, "utf-8");
    } catch {
      return; // no existing log — fresh queue
    }
    for (const line of content.split("\n")) {
      if (!line.trim()) continue;
      try {
        const entry = JSON.parse(line) as LogLine;
        this.applyLogLine(entry);
      } catch {
        // A partially-written final line from a crash mid-write is
        // skipped, not fatal — every prior line is still replayed.
      }
    }
  }

  private applyLogLine(entry: LogLine): void {
    if (entry.op === "put") {
      this.rows.set(entry.id, entry.row);
    } else if (entry.op === "retry") {
      const row = this.rows.get(entry.id);
      if (row) {
        row.attempts = entry.attempts;
        row.nextRetryAt = entry.nextRetryAt;
      }
    } else if (entry.op === "ack") {
      this.rows.delete(entry.id);
    }
  }

  private appendLog(entry: LogLine): void {
    if (!this.path || this.closed) return;
    const line = `${JSON.stringify(entry)}\n`;
    this.writeQueue = this.writeQueue.then(async () => {
      if (this.closed) return;
      await appendFile(this.path as string, line, "utf-8");
      this.opsSinceCompaction += 1;
      if (this.opsSinceCompaction >= 500) {
        this.opsSinceCompaction = 0;
        await this.compact();
      }
    });
  }

  private async compact(): Promise<void> {
    if (!this.path || this.closed) return;
    const lines = [...this.rows.entries()].map(([id, row]) =>
      JSON.stringify({ op: "put", id, row } satisfies LogLine),
    );
    const tmpPath = `${this.path}.tmp`;
    await writeFile(tmpPath, lines.length > 0 ? `${lines.join("\n")}\n` : "", "utf-8");
    await rename(tmpPath, this.path);
  }

  async whenReady(): Promise<void> {
    await this.ready;
  }

  enqueue(event: QueuedEvent): void {
    const row: Row = {
      payload: event.payload,
      attempts: event.attempts,
      createdAt: Date.now(),
      nextRetryAt: 0,
    };
    this.rows.set(event.eventId, row);
    this.appendLog({ op: "put", id: event.eventId, row });
  }

  enqueueMany(events: QueuedEvent[]): void {
    for (const event of events) this.enqueue(event);
  }

  dequeueDue(limit: number): QueuedEvent[] {
    const now = Date.now();
    const due = [...this.rows.entries()]
      .filter(([, row]) => row.nextRetryAt <= now)
      .sort((a, b) => a[1].createdAt - b[1].createdAt)
      .slice(0, limit);
    return due.map(([id, row]) => ({ eventId: id, payload: row.payload, attempts: row.attempts }));
  }

  markRetry(eventId: string, attempts: number, nextRetryAt: number): void {
    const row = this.rows.get(eventId);
    if (!row) return;
    row.attempts = attempts;
    row.nextRetryAt = nextRetryAt;
    this.appendLog({ op: "retry", id: eventId, attempts, nextRetryAt });
  }

  ack(eventId: string): void {
    this.rows.delete(eventId);
    this.appendLog({ op: "ack", id: eventId });
  }

  ackMany(eventIds: string[]): void {
    for (const id of eventIds) this.ack(id);
  }

  count(): number {
    return this.rows.size;
  }

  async close(): Promise<void> {
    if (this.closed) return;
    await this.writeQueue;
    this.closed = true;
  }
}
