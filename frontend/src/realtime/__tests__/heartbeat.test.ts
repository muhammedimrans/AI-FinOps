import { describe, expect, it } from "vitest";
import { HeartbeatMonitor } from "../heartbeat";

describe("HeartbeatMonitor", () => {
  it("returns a pong frame and records timing on handlePing", () => {
    const hb = new HeartbeatMonitor();
    const pong = hb.handlePing(1_000);
    expect(pong).toEqual({ type: "pong" });

    const snap = hb.snapshot();
    expect(snap.lastPingReceivedAt).toBe(1_000);
    expect(snap.lastPongSentAt).not.toBeNull();
    expect(snap.replyLatencyMs).not.toBeNull();
  });

  it("starts with an empty snapshot", () => {
    const hb = new HeartbeatMonitor();
    expect(hb.snapshot()).toEqual({
      lastPingReceivedAt: null,
      lastPongSentAt: null,
      replyLatencyMs: null,
    });
  });

  it("is not stale before any ping has been received", () => {
    const hb = new HeartbeatMonitor();
    expect(hb.isStale()).toBe(false);
  });

  it("is not stale shortly after a ping", () => {
    const hb = new HeartbeatMonitor();
    hb.handlePing(10_000);
    expect(hb.isStale(15_000)).toBe(false);
  });

  it("is stale once well past the 30s heartbeat interval + margin", () => {
    const hb = new HeartbeatMonitor();
    hb.handlePing(10_000);
    expect(hb.isStale(10_000 + 50_000)).toBe(true);
  });

  it("reset clears all recorded timing", () => {
    const hb = new HeartbeatMonitor();
    hb.handlePing(1_000);
    hb.reset();
    expect(hb.snapshot()).toEqual({
      lastPingReceivedAt: null,
      lastPongSentAt: null,
      replyLatencyMs: null,
    });
  });
});
