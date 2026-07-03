import { useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import { useRealtimeEvent } from "./hooks";

// Query key prefixes affected by a usage.created event, in
// hooks/useDashboard.ts. Every one of these hooks keys its query on
// [prefix, organizationId, ...filters] — invalidating by prefix alone
// (React Query matches partial keys) refetches every filter combination
// currently mounted, not just today's date range.
const USAGE_AFFECTED_QUERY_PREFIXES = [
  "overview",
  "time-series",
  "providers",
  "models",
  "projects",
  "organization",
  "recent-activity",
] as const;

// Coalesce a burst of events (e.g. several requests landing within the
// same second) into one refetch instead of one per event — refetching on
// every single event would turn a busy organization's dashboard into a
// request storm.
const INVALIDATION_DEBOUNCE_MS = 1_500;

/**
 * Bridges live `usage.created` events into the existing React Query cache.
 * Mount once (see `AppLayout`) — every dashboard page keeps using its
 * normal `useOverview()`/`useTimeSeries()`/etc. hooks unmodified; this just
 * makes their cached data go stale (and therefore refetch) the moment a
 * live event says there's something new, instead of waiting for the next
 * poll. When the connection isn't healthy, `useRealtimeRefetchInterval`
 * (used by those same hooks) takes over with time-based polling instead.
 */
export function useRealtimeQueryBridge(): void {
  const queryClient = useQueryClient();
  const organizationId = useOrgStore((s) => s.organizationId);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useRealtimeEvent("usage.created", () => {
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      for (const prefix of USAGE_AFFECTED_QUERY_PREFIXES) {
        void queryClient.invalidateQueries({ queryKey: [prefix, organizationId] });
      }
    }, INVALIDATION_DEBOUNCE_MS);
  });
}
