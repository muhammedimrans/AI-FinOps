import {
  buildWebSocketUrl,
  isRetryableCloseCode,
  reconnectDelayMs,
  WS_CLOSE_AUTH_FAILED,
} from "./connection";
import { parseRealtimeFrame } from "./events";
import { HeartbeatMonitor } from "./heartbeat";
import { isServerPing, type ConnectionSnapshot, type ConnectionStatus, type RealtimeEvent } from "./types";

// EP-24.4.1 — see scheduleReconnect() below for why this exists.
export const MAX_RECONNECT_ATTEMPTS = 10;

/** EP-19.4 — cheap, always-on diagnostic breadcrumbs (console.debug is
 * invisible in devtools unless "Verbose" level is enabled, so this costs
 * nothing in normal use) for the exact lifecycle events a WebSocket
 * regression investigation needs: connect, heartbeat ping/pong, close
 * code/reason. Companion to the structured server-side logs added in
 * `app/api/v1/realtime.py`'s own EP-19.4 fix. */
function logRealtime(event: string, detail: Record<string, unknown>): void {
  console.debug(`[realtime] ${event}`, { ...detail, ts: new Date().toISOString() });
}

export interface RealtimeClientOptions {
  baseUrl?: string;
  /** Returns the current access token at connect/reconnect time — a
   * function, not a string, so a token refreshed mid-session is picked up
   * on the next reconnect without the caller having to re-wire anything. */
  getToken: () => string | null;
  organizationId: string;
  onEvent: (event: RealtimeEvent) => void;
  onStatusChange: (snapshot: ConnectionSnapshot) => void;
}

/**
 * Thin wrapper around the browser's native `WebSocket` — reconnects with
 * backoff, answers heartbeats, and reports connection state. No external
 * WebSocket library: the platform API is sufficient and this keeps the
 * bundle dependency-free.
 *
 * One instance = one organization's stream. Switching organizations means
 * disposing this instance and creating a new one (see `subscriptions.ts`),
 * matching the backend's model where a connection *is* joined to exactly
 * one organization for its whole lifetime.
 */
export class RealtimeClient {
  private socket: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeat = new HeartbeatMonitor();
  private disposed = false;
  private reconnectAttempts = 0;
  private status: ConnectionStatus = "connecting";
  private lastConnectedAt: number | null = null;
  private lastError: string | null = null;

  constructor(private readonly options: RealtimeClientOptions) {}

  connect(): void {
    if (this.disposed) return;
    const token = this.options.getToken();
    if (!token) {
      this.setStatus("auth_failed", "No access token available");
      return;
    }

    this.setStatus(this.reconnectAttempts > 0 ? "reconnecting" : "connecting");

    const url = buildWebSocketUrl({
      ...(this.options.baseUrl !== undefined ? { baseUrl: this.options.baseUrl } : {}),
      token,
      organizationId: this.options.organizationId,
    });

    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch (err) {
      this.scheduleReconnect(err instanceof Error ? err.message : "Failed to open socket");
      return;
    }
    this.socket = socket;

    socket.addEventListener("open", () => {
      if (this.disposed) return;
      this.reconnectAttempts = 0;
      this.lastConnectedAt = Date.now();
      this.heartbeat.reset();
      this.setStatus("connected");
      // EP-19.4 — lightweight instrumentation for diagnosing connection
      // regressions in production (console.debug: free at runtime, invisible
      // unless devtools' "Verbose" log level is on). Mirrors the server-side
      // structured logs added in app/api/v1/realtime.py's own EP-19.4 fix.
      logRealtime("connected", { organizationId: this.options.organizationId });
    });

    socket.addEventListener("message", (evt) => {
      if (this.disposed) return;
      this.handleFrame(typeof evt.data === "string" ? evt.data : "");
    });

    socket.addEventListener("close", (evt) => {
      if (this.disposed) return;
      this.socket = null;
      logRealtime("closed", {
        code: evt.code,
        reason: evt.reason || null,
        wasClean: evt.wasClean,
        organizationId: this.options.organizationId,
      });
      if (evt.code === WS_CLOSE_AUTH_FAILED) {
        this.setStatus("auth_failed", evt.reason || "Authentication failed");
        return;
      }
      if (!isRetryableCloseCode(evt.code)) {
        this.setStatus("offline", evt.reason || `Closed (${evt.code})`);
        return;
      }
      this.scheduleReconnect(evt.reason || `Connection closed (${evt.code})`);
    });

    socket.addEventListener("error", () => {
      // The browser fires a generic Event with no detail; the close event
      // that follows carries the actual code/reason, so this is a no-op
      // beyond letting `close` do the real handling.
    });
  }

  /** Call after an organization switch or a fresh login — tears down any
   * existing socket and opens a new one against the (possibly new) token
   * and organization captured by the caller. */
  reconnectNow(): void {
    this.reconnectAttempts = 0;
    this.teardownSocket();
    this.connect();
  }

  disconnect(): void {
    this.disposed = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.teardownSocket();
  }

  getSnapshot(): ConnectionSnapshot {
    const hb = this.heartbeat.snapshot();
    return {
      status: this.status,
      organizationId: this.options.organizationId,
      reconnectAttempts: this.reconnectAttempts,
      lastConnectedAt: this.lastConnectedAt,
      lastHeartbeatAt: hb.lastPingReceivedAt,
      heartbeatLatencyMs: hb.replyLatencyMs,
      lastError: this.lastError,
    };
  }

  private handleFrame(raw: string): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return; // malformed frame — never crash the connection over it
    }

    if (isServerPing(parsed)) {
      logRealtime("heartbeat_ping_received", { organizationId: this.options.organizationId });
      const pong = this.heartbeat.handlePing();
      this.socket?.send(JSON.stringify(pong));
      logRealtime("heartbeat_pong_sent", {
        organizationId: this.options.organizationId,
        replyLatencyMs: this.heartbeat.snapshot().replyLatencyMs,
      });
      // Heartbeat timing changed — republish the snapshot for the status UI.
      this.setStatus(this.status);
      return;
    }

    const event = parseRealtimeFrame(raw);
    if (event) this.options.onEvent(event);
  }

  private scheduleReconnect(reason: string): void {
    // EP-24.4.1: bounded retry count, not just bounded per-attempt delay —
    // an unbounded number of attempts (even at a capped 30s cadence) is
    // still an infinite reconnect loop over a long-lived tab. After
    // MAX_RECONNECT_ATTEMPTS, give up and report "offline"; the React
    // Query bridge already falls back to polling for any non-"connected"
    // status (see useRealtimeRefetchInterval), so the dashboard keeps
    // working — reconnectNow() (org switch / fresh login) resets the
    // counter and tries again.
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      logRealtime("reconnect_abandoned", {
        organizationId: this.options.organizationId,
        attempts: this.reconnectAttempts,
      });
      this.setStatus("offline", `Gave up reconnecting after ${MAX_RECONNECT_ATTEMPTS} attempts`);
      return;
    }
    this.lastError = reason;
    this.setStatus("reconnecting", reason);
    const delay = reconnectDelayMs(this.reconnectAttempts);
    this.reconnectAttempts += 1;
    logRealtime("reconnect_scheduled", {
      organizationId: this.options.organizationId,
      attempt: this.reconnectAttempts,
      delayMs: delay,
      reason,
    });
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private teardownSocket(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      const socket = this.socket;
      this.socket = null;
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.onerror = null;
      try {
        socket.close(1000, "client disconnect");
      } catch {
        // Already closed/closing — nothing to do.
      }
    }
  }

  private setStatus(status: ConnectionStatus, error: string | null = null): void {
    this.status = status;
    if (error !== null) this.lastError = error;
    this.options.onStatusChange(this.getSnapshot());
  }
}
