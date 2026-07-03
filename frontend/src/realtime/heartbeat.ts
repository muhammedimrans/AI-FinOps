/**
 * Heartbeat bookkeeping — transport-agnostic and pure so it's unit
 * testable without a real WebSocket. The backend (`app/api/v1/realtime.py`)
 * sends `{"type":"ping"}` every 30s and closes the connection with code
 * 4408 if it doesn't see any client frame back within 10s; disconnecting a
 * stale client is entirely the server's job. This module's job is just to:
 * (1) reply immediately whenever a ping arrives, and (2) track enough
 * timing for the connection-status UI to show "healthy" vs. "stale".
 */

const STALE_THRESHOLD_MS = 45_000; // one missed 30s heartbeat + margin

export interface HeartbeatSnapshot {
  lastPingReceivedAt: number | null;
  lastPongSentAt: number | null;
  /** Time between receiving a ping and sending the pong reply — not true
   * network RTT (the server doesn't echo a timestamp), but a useful proxy
   * for "is this tab's event loop keeping up". */
  replyLatencyMs: number | null;
}

export class HeartbeatMonitor {
  private lastPingReceivedAt: number | null = null;
  private lastPongSentAt: number | null = null;
  private replyLatencyMs: number | null = null;

  /** Call when a `{"type":"ping"}` frame arrives. Returns the pong frame to
   * send back — the caller (client.ts) owns actually writing to the socket. */
  handlePing(now: number = Date.now()): { type: "pong" } {
    this.lastPingReceivedAt = now;
    const sentAt = Date.now();
    this.lastPongSentAt = sentAt;
    this.replyLatencyMs = Math.max(0, sentAt - now);
    return { type: "pong" };
  }

  snapshot(): HeartbeatSnapshot {
    return {
      lastPingReceivedAt: this.lastPingReceivedAt,
      lastPongSentAt: this.lastPongSentAt,
      replyLatencyMs: this.replyLatencyMs,
    };
  }

  /** True if no heartbeat has been seen recently enough to trust the
   * connection is still healthy (used to drive a "stale" UI state before
   * the server's own 4408 disconnect actually lands). */
  isStale(now: number = Date.now()): boolean {
    if (this.lastPingReceivedAt === null) return false;
    return now - this.lastPingReceivedAt > STALE_THRESHOLD_MS;
  }

  reset(): void {
    this.lastPingReceivedAt = null;
    this.lastPongSentAt = null;
    this.replyLatencyMs = null;
  }
}
