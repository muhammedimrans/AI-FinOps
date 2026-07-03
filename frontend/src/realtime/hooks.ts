import { useEffect, useRef } from "react";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";
import { realtimeSubscriptions } from "./subscriptions";
import { useRealtimeStore } from "./store";
import type { RealtimeEvent, RealtimeEventType } from "./types";

/**
 * Mounts the real-time connection for as long as the component is mounted
 * and the user is authenticated with an active organization — mount this
 * once, high in the tree (see `AppLayout`). Reacts to token refreshes and
 * organization switches automatically; no consumer wiring required beyond
 * mounting it once.
 */
export function useRealtimeConnection(): void {
  const accessToken = useAuthStore((s) => s.accessToken);
  const organizationId = useOrgStore((s) => s.organizationId);

  useEffect(() => {
    if (!accessToken || !organizationId) {
      realtimeSubscriptions.stop();
      return;
    }
    realtimeSubscriptions.start(() => useAuthStore.getState().accessToken, organizationId);
    return () => realtimeSubscriptions.stop();
    // Re-run on token/org identity change only — `getToken` always reads
    // fresh state, so a token *rotation* alone doesn't need a teardown.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken !== null, organizationId]);

  // A refreshed token should nudge a connection that's sitting in
  // `auth_failed` to retry immediately rather than wait for its own
  // (nonexistent) retry timer.
  const status = useRealtimeStore((s) => s.connection.status);
  useEffect(() => {
    if (status === "auth_failed" && accessToken) {
      realtimeSubscriptions.reconnectNow();
    }
  }, [status, accessToken]);
}

export function useConnectionStatus() {
  return useRealtimeStore((s) => s.connection);
}

export function useLiveActivity(limit?: number) {
  const activity = useRealtimeStore((s) => s.recentActivity);
  return limit ? activity.slice(0, limit) : activity;
}

export function useLiveMetrics() {
  return useRealtimeStore((s) => s.liveMetrics);
}

export function useUnreadNotificationCount() {
  return useRealtimeStore((s) => s.unreadNotificationCount);
}

export function useLatestEvent(type: RealtimeEventType) {
  return useRealtimeStore((s) => s.lastEventByType[type]);
}

/**
 * Returns `false` (no polling) while the real-time connection is healthy,
 * or `fallbackMs` otherwise — the "when disconnected, polling resumes
 * automatically" half of the ticket's React Query integration. Pass this
 * straight into a query's `refetchInterval` option.
 */
export function useRealtimeRefetchInterval(fallbackMs: number): number | false {
  const status = useRealtimeStore((s) => s.connection.status);
  return status === "connected" ? false : fallbackMs;
}

/**
 * Subscribes `handler` to one event type (or `"*"` for all) for the
 * lifetime of the calling component. `handler` is captured fresh on every
 * render via a ref, so callers don't need to `useCallback` it.
 */
export function useRealtimeEvent(
  type: RealtimeEventType | "*",
  handler: (event: RealtimeEvent) => void,
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    return realtimeSubscriptions.subscribe(type, (event) => handlerRef.current(event));
  }, [type]);
}
