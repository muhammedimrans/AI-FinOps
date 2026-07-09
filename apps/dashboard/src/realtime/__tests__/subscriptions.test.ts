import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { realtimeSubscriptions } from "../subscriptions";
import { useRealtimeStore } from "../store";
import type { RealtimeEvent } from "../types";

type Listener = (evt: unknown) => void;

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static reset() {
    FakeWebSocket.instances = [];
  }
  url: string;
  private listeners: Record<string, Listener[]> = {};
  closedWith: { code: number; reason: string } | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }
  addEventListener(type: string, cb: Listener) {
    (this.listeners[type] ??= []).push(cb);
  }
  send() {
    /* no-op for these tests */
  }
  close(code = 1000, reason = "") {
    this.closedWith = { code, reason };
    this.emit("close", { code, reason });
  }
  emit(type: string, evt: unknown) {
    for (const cb of this.listeners[type] ?? []) cb(evt);
  }
}

function makeEvent(overrides: Partial<RealtimeEvent> = {}): RealtimeEvent {
  return {
    event_id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    organization_id: "org-1",
    type: "usage.created",
    version: 1,
    payload: { provider: "openai" },
    trace_id: null,
    correlation_id: null,
    ...overrides,
  };
}

describe("realtimeSubscriptions", () => {
  beforeEach(() => {
    FakeWebSocket.reset();
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });

  afterEach(() => {
    realtimeSubscriptions.stop();
    vi.unstubAllGlobals();
  });

  it("start() opens exactly one connection for the given organization", () => {
    realtimeSubscriptions.start(() => "token", "org-1");
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("starting again with the same organization does not open a second connection", () => {
    realtimeSubscriptions.start(() => "token", "org-1");
    realtimeSubscriptions.start(() => "token", "org-1");
    expect(FakeWebSocket.instances).toHaveLength(1);
  });

  it("switching organizations tears down the old connection, resets store, and opens a new one", () => {
    realtimeSubscriptions.start(() => "token", "org-1");
    const first = FakeWebSocket.instances[0]!;
    first.emit("open", {});
    first.emit("message", { data: JSON.stringify(makeEvent()) });
    expect(useRealtimeStore.getState().recentActivity).toHaveLength(1);

    realtimeSubscriptions.start(() => "token", "org-2");

    expect(first.closedWith).not.toBeNull();
    expect(FakeWebSocket.instances).toHaveLength(2);
    // Switching organizations must clear stale live data — no cross-org leakage.
    // The store briefly flips to "organization_changed" during the reset,
    // then immediately to "connecting" as the new socket opens — by the
    // time start() returns, "connecting" is the settled status.
    expect(useRealtimeStore.getState().recentActivity).toHaveLength(0);
    expect(useRealtimeStore.getState().connection.status).toBe("connecting");
  });

  it("dispatches an incoming event to a type-specific subscriber", () => {
    realtimeSubscriptions.start(() => "token", "org-1");
    const socket = FakeWebSocket.instances[0]!;
    socket.emit("open", {});

    const received: RealtimeEvent[] = [];
    const unsubscribe = realtimeSubscriptions.subscribe("usage.created", (e) => received.push(e));

    socket.emit("message", { data: JSON.stringify(makeEvent()) });
    expect(received).toHaveLength(1);

    unsubscribe();
    socket.emit("message", { data: JSON.stringify(makeEvent()) });
    expect(received).toHaveLength(1); // no further delivery after unsubscribe
  });

  it("a wildcard ('*') subscriber receives every event type", () => {
    realtimeSubscriptions.start(() => "token", "org-1");
    const socket = FakeWebSocket.instances[0]!;
    socket.emit("open", {});

    const received: RealtimeEvent[] = [];
    realtimeSubscriptions.subscribe("*", (e) => received.push(e));

    socket.emit("message", { data: JSON.stringify(makeEvent({ type: "usage.created" })) });
    socket.emit("message", { data: JSON.stringify(makeEvent({ type: "provider.error" })) });
    expect(received.map((e) => e.type)).toEqual(["usage.created", "provider.error"]);
  });

  it("stop() closes the connection and clears organization tracking", () => {
    realtimeSubscriptions.start(() => "token", "org-1");
    const socket = FakeWebSocket.instances[0]!;
    realtimeSubscriptions.stop();
    expect(socket.closedWith).not.toBeNull();

    // A subsequent start() for the same org opens a fresh connection (proves
    // stop() actually cleared internal tracking rather than treating this as
    // a no-op "already running" case).
    realtimeSubscriptions.start(() => "token", "org-1");
    expect(FakeWebSocket.instances).toHaveLength(2);
  });
});
