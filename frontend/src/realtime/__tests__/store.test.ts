import { beforeEach, describe, expect, it } from "vitest";
import { useRealtimeStore } from "../store";
import type { RealtimeEvent } from "../types";

function usageEvent(overrides: Partial<RealtimeEvent> = {}): RealtimeEvent {
  return {
    event_id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    organization_id: "org-1",
    type: "usage.created",
    version: 1,
    payload: { provider: "openai", model: "gpt-4.1", cost: "1.50", total_tokens: 100 },
    trace_id: null,
    correlation_id: null,
    ...overrides,
  };
}

describe("useRealtimeStore", () => {
  beforeEach(() => {
    useRealtimeStore.setState({
      connection: {
        status: "connecting",
        organizationId: null,
        reconnectAttempts: 0,
        lastConnectedAt: null,
        lastHeartbeatAt: null,
        heartbeatLatencyMs: null,
        lastError: null,
      },
      recentActivity: [],
      activityLimit: 200,
      lastEventByType: {},
      liveMetrics: {
        costDelta: 0,
        tokensDelta: 0,
        requestCount: 0,
        providersSeen: new Set(),
        modelsSeen: new Set(),
      },
    });
  });

  it("ingestEvent prepends to recentActivity (newest first)", () => {
    const e1 = usageEvent();
    const e2 = usageEvent();
    useRealtimeStore.getState().ingestEvent(e1);
    useRealtimeStore.getState().ingestEvent(e2);
    const activity = useRealtimeStore.getState().recentActivity;
    expect(activity[0]).toBe(e2);
    expect(activity[1]).toBe(e1);
  });

  it("caps recentActivity at activityLimit", () => {
    useRealtimeStore.getState().setActivityLimit(3);
    for (let i = 0; i < 5; i++) useRealtimeStore.getState().ingestEvent(usageEvent());
    expect(useRealtimeStore.getState().recentActivity).toHaveLength(3);
  });

  it("accumulates cost/token/request deltas for usage.created events", () => {
    useRealtimeStore.getState().ingestEvent(
      usageEvent({ payload: { provider: "openai", model: "gpt-4.1", cost: "1.50", total_tokens: 100 } }),
    );
    useRealtimeStore.getState().ingestEvent(
      usageEvent({ payload: { provider: "anthropic", model: "claude", cost: "2.25", total_tokens: 50 } }),
    );
    const metrics = useRealtimeStore.getState().liveMetrics;
    expect(metrics.costDelta).toBeCloseTo(3.75);
    expect(metrics.tokensDelta).toBe(150);
    expect(metrics.requestCount).toBe(2);
    expect(metrics.providersSeen.has("openai")).toBe(true);
    expect(metrics.providersSeen.has("anthropic")).toBe(true);
    expect(metrics.modelsSeen.has("gpt-4.1")).toBe(true);
  });

  it("does not touch liveMetrics for non-usage.created events", () => {
    useRealtimeStore.getState().ingestEvent(
      usageEvent({ type: "provider.error", payload: { provider: "openai" } }),
    );
    expect(useRealtimeStore.getState().liveMetrics.requestCount).toBe(0);
  });

  it("tracks the last event seen per type", () => {
    const errorEvent = usageEvent({ type: "provider.error", payload: {} });
    useRealtimeStore.getState().ingestEvent(usageEvent());
    useRealtimeStore.getState().ingestEvent(errorEvent);
    expect(useRealtimeStore.getState().lastEventByType["provider.error"]).toBe(errorEvent);
  });

  it("resetForOrganizationChange clears activity, metrics, and last-event cache", () => {
    useRealtimeStore.getState().ingestEvent(usageEvent());
    useRealtimeStore.getState().resetForOrganizationChange();

    const state = useRealtimeStore.getState();
    expect(state.recentActivity).toEqual([]);
    expect(state.lastEventByType).toEqual({});
    expect(state.liveMetrics.requestCount).toBe(0);
    expect(state.liveMetrics.providersSeen.size).toBe(0);
    expect(state.connection.status).toBe("organization_changed");
  });

  it("setConnection replaces the connection snapshot wholesale", () => {
    useRealtimeStore.getState().setConnection({
      status: "connected",
      organizationId: "org-1",
      reconnectAttempts: 2,
      lastConnectedAt: 123,
      lastHeartbeatAt: 456,
      heartbeatLatencyMs: 12,
      lastError: null,
    });
    expect(useRealtimeStore.getState().connection.status).toBe("connected");
    expect(useRealtimeStore.getState().connection.reconnectAttempts).toBe(2);
  });
});
