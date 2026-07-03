import { create } from "zustand";
import type { ConnectionSnapshot, RealtimeEvent, RealtimeEventType } from "./types";

const DEFAULT_ACTIVITY_LIMIT = 200;

export interface LiveMetricsDelta {
  /** Sum of `usage.created` costs received since the socket last (re)connected —
   * a delta to nudge the polled KPI total with, not a replacement for it. */
  costDelta: number;
  tokensDelta: number;
  requestCount: number;
  providersSeen: ReadonlySet<string>;
  modelsSeen: ReadonlySet<string>;
}

interface RealtimeState {
  connection: ConnectionSnapshot;
  /** Most recent events, newest first, capped at `activityLimit` — this is
   * the frontend's own local "replay buffer": a component that mounts after
   * an event already arrived (e.g. the user just opened the activity panel)
   * still has recent history to render immediately. It is NOT a substitute
   * for the backend's SSE `Last-Event-ID` replay — a WebSocket connection
   * that drops mid-session and reconnects does not recover events it missed
   * while offline; see docs/realtime/TROUBLESHOOTING.md. */
  recentActivity: RealtimeEvent[];
  activityLimit: number;
  lastEventByType: Partial<Record<RealtimeEventType, RealtimeEvent>>;
  liveMetrics: LiveMetricsDelta;
  unreadNotificationCount: number;

  setConnection: (snapshot: ConnectionSnapshot) => void;
  ingestEvent: (event: RealtimeEvent) => void;
  incrementUnread: () => void;
  clearUnread: () => void;
  setActivityLimit: (limit: number) => void;
  resetForOrganizationChange: () => void;
}

const emptyMetrics = (): LiveMetricsDelta => ({
  costDelta: 0,
  tokensDelta: 0,
  requestCount: 0,
  providersSeen: new Set(),
  modelsSeen: new Set(),
});

const initialConnection: ConnectionSnapshot = {
  status: "connecting",
  organizationId: null,
  reconnectAttempts: 0,
  lastConnectedAt: null,
  lastHeartbeatAt: null,
  heartbeatLatencyMs: null,
  lastError: null,
};

export const useRealtimeStore = create<RealtimeState>()((set, get) => ({
  connection: initialConnection,
  recentActivity: [],
  activityLimit: DEFAULT_ACTIVITY_LIMIT,
  lastEventByType: {},
  liveMetrics: emptyMetrics(),
  unreadNotificationCount: 0,

  setConnection: (snapshot) => set({ connection: snapshot }),

  ingestEvent: (event) => {
    const { activityLimit, liveMetrics } = get();

    const nextActivity = [event, ...get().recentActivity].slice(0, activityLimit);
    const nextByType = { ...get().lastEventByType, [event.type]: event };

    let nextMetrics = liveMetrics;
    if (event.type === "usage.created") {
      const payload = event.payload as {
        cost?: string;
        total_tokens?: number;
        provider?: string;
        model?: string;
      };
      const cost = Number.parseFloat(payload.cost ?? "0");
      const tokens = Number(payload.total_tokens ?? 0);
      const providersSeen = new Set(liveMetrics.providersSeen);
      const modelsSeen = new Set(liveMetrics.modelsSeen);
      if (payload.provider) providersSeen.add(payload.provider);
      if (payload.model) modelsSeen.add(payload.model);
      nextMetrics = {
        costDelta: liveMetrics.costDelta + (Number.isFinite(cost) ? cost : 0),
        tokensDelta: liveMetrics.tokensDelta + (Number.isFinite(tokens) ? tokens : 0),
        requestCount: liveMetrics.requestCount + 1,
        providersSeen,
        modelsSeen,
      };
    }

    set({
      recentActivity: nextActivity,
      lastEventByType: nextByType,
      liveMetrics: nextMetrics,
    });
  },

  incrementUnread: () => set((s) => ({ unreadNotificationCount: s.unreadNotificationCount + 1 })),
  clearUnread: () => set({ unreadNotificationCount: 0 }),
  setActivityLimit: (limit) =>
    set((s) => ({
      activityLimit: limit,
      recentActivity: s.recentActivity.slice(0, limit),
    })),

  /** Called when the user switches organizations — per the ticket's
   * connection flow, all stale live data must be cleared before resuming
   * streaming under the new organization, so a stray render never shows one
   * org's live numbers under another org's context. */
  resetForOrganizationChange: () =>
    set({
      recentActivity: [],
      lastEventByType: {},
      liveMetrics: emptyMetrics(),
      unreadNotificationCount: 0,
      connection: { ...initialConnection, status: "organization_changed" },
    }),
}));
