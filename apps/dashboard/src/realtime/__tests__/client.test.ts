import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MAX_RECONNECT_ATTEMPTS, RealtimeClient } from "../client";
import { WS_CLOSE_AUTH_FAILED } from "../connection";
import type { ConnectionSnapshot, RealtimeEvent } from "../types";

type Listener = (evt: unknown) => void;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static reset() {
    FakeWebSocket.instances = [];
  }

  url: string;
  sent: string[] = [];
  closedWith: { code: number; reason: string } | null = null;
  private listeners: Record<string, Listener[]> = {};

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type: string, cb: Listener): void {
    (this.listeners[type] ??= []).push(cb);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(code = 1000, reason = ""): void {
    this.closedWith = { code, reason };
    this.emit("close", { code, reason });
  }

  emit(type: string, evt: unknown): void {
    for (const cb of this.listeners[type] ?? []) cb(evt);
  }
}

function makeEvent(overrides: Partial<RealtimeEvent> = {}): RealtimeEvent {
  return {
    event_id: "11111111-1111-1111-1111-111111111111",
    timestamp: "2026-07-03T12:00:00Z",
    organization_id: "org-1",
    type: "usage.created",
    version: 1,
    payload: { provider: "openai" },
    trace_id: null,
    correlation_id: null,
    ...overrides,
  };
}

describe("RealtimeClient", () => {
  let statusChanges: ConnectionSnapshot[];
  let events: RealtimeEvent[];
  let client: RealtimeClient;

  beforeEach(() => {
    FakeWebSocket.reset();
    vi.stubGlobal("WebSocket", FakeWebSocket);
    vi.useFakeTimers();
    statusChanges = [];
    events = [];
    client = new RealtimeClient({
      baseUrl: "http://localhost:8000",
      getToken: () => "test-token",
      organizationId: "org-1",
      onEvent: (e) => events.push(e),
      onStatusChange: (s) => statusChanges.push(s),
    });
  });

  afterEach(() => {
    client.disconnect();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("goes auth_failed immediately when there is no token, without opening a socket", () => {
    const noTokenClient = new RealtimeClient({
      getToken: () => null,
      organizationId: "org-1",
      onEvent: () => {},
      onStatusChange: (s) => statusChanges.push(s),
    });
    noTokenClient.connect();
    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(statusChanges.at(-1)?.status).toBe("auth_failed");
  });

  it("reports connecting then connected on a successful handshake", () => {
    client.connect();
    expect(statusChanges.at(-1)?.status).toBe("connecting");

    FakeWebSocket.instances[0]!.emit("open", {});
    expect(statusChanges.at(-1)?.status).toBe("connected");
  });

  it("replies to a server heartbeat ping with a pong frame", () => {
    client.connect();
    const socket = FakeWebSocket.instances[0]!;
    socket.emit("open", {});
    socket.emit("message", { data: JSON.stringify({ type: "ping" }) });

    expect(socket.sent).toHaveLength(1);
    expect(JSON.parse(socket.sent[0]!)).toEqual({ type: "pong" });
  });

  it("forwards a well-formed real-time event to onEvent", () => {
    client.connect();
    const socket = FakeWebSocket.instances[0]!;
    socket.emit("open", {});
    socket.emit("message", { data: JSON.stringify(makeEvent()) });

    expect(events).toHaveLength(1);
    expect(events[0]!.type).toBe("usage.created");
  });

  it("ignores a malformed message frame without throwing", () => {
    client.connect();
    const socket = FakeWebSocket.instances[0]!;
    socket.emit("open", {});
    expect(() => socket.emit("message", { data: "{not json" })).not.toThrow();
    expect(events).toHaveLength(0);
  });

  it("goes auth_failed on a 4401 close and does not schedule a reconnect", () => {
    client.connect();
    const socket = FakeWebSocket.instances[0]!;
    socket.emit("open", {});
    socket.emit("close", { code: WS_CLOSE_AUTH_FAILED, reason: "Invalid token" });

    expect(statusChanges.at(-1)?.status).toBe("auth_failed");
    vi.advanceTimersByTime(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1); // no reconnect attempt made
  });

  it("schedules a reconnect with backoff on a retryable close code", () => {
    client.connect();
    const socket = FakeWebSocket.instances[0]!;
    socket.emit("open", {});
    socket.emit("close", { code: 1006, reason: "abnormal closure" });

    expect(statusChanges.at(-1)?.status).toBe("reconnecting");
    expect(FakeWebSocket.instances).toHaveLength(1);

    vi.advanceTimersByTime(5_000);
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });

  it("reconnectNow tears down the existing socket and connects immediately", () => {
    client.connect();
    FakeWebSocket.instances[0]!.emit("open", {});
    client.reconnectNow();

    expect(FakeWebSocket.instances[0]!.closedWith).not.toBeNull();
    expect(FakeWebSocket.instances).toHaveLength(2);
  });

  it("disconnect closes the socket and prevents any further reconnect", () => {
    client.connect();
    const socket = FakeWebSocket.instances[0]!;
    socket.emit("open", {});
    client.disconnect();

    expect(socket.closedWith).not.toBeNull();
    socket.emit("close", { code: 1006, reason: "late close after disconnect" });
    vi.advanceTimersByTime(60_000);
    expect(FakeWebSocket.instances).toHaveLength(1); // disposed — no reconnect
  });

  it("getSnapshot reflects the organization id and reconnect attempts", () => {
    client.connect();
    expect(client.getSnapshot().organizationId).toBe("org-1");
    expect(client.getSnapshot().reconnectAttempts).toBe(0);
  });

  it("stops retrying and reports offline after MAX_RECONNECT_ATTEMPTS (EP-24.4.1)", () => {
    client.connect();
    for (let i = 0; i < MAX_RECONNECT_ATTEMPTS; i++) {
      const socket = FakeWebSocket.instances.at(-1)!;
      socket.emit("close", { code: 1006, reason: "abnormal closure" });
      // Advance past whatever backoff delay this attempt scheduled.
      vi.advanceTimersByTime(60_000);
    }
    // One more close after the cap is reached must not open another socket.
    const countBeforeFinalClose = FakeWebSocket.instances.length;
    const lastSocket = FakeWebSocket.instances.at(-1)!;
    lastSocket.emit("close", { code: 1006, reason: "abnormal closure" });
    vi.advanceTimersByTime(60_000);

    expect(statusChanges.at(-1)?.status).toBe("offline");
    expect(FakeWebSocket.instances.length).toBe(countBeforeFinalClose);
  });
});
