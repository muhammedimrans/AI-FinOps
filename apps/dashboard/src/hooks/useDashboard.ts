import { useQuery } from "@tanstack/react-query";
import { useUIStore } from "../stores/ui";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import { useRealtimeRefetchInterval } from "../realtime/hooks";

// Polling fallback cadence when the real-time connection isn't healthy.
// While connected, these queries take live updates instead — see
// realtime/queryBridge.ts — and this interval is disabled entirely.
const POLL_FALLBACK_MS = 60 * 1000;

function useFilters() {
  const { startDate, endDate, currency, granularity } = useUIStore();
  const { organizationId } = useOrgStore();
  return { start_date: startDate, end_date: endDate, currency, granularity, organizationId };
}

// EP-24.1 — optional dimension filters shared by every breakdown hook below.
// Narrowing to one project/provider/model reuses the exact same endpoints
// (now filter-aware server-side) rather than a second query shape.
export interface DimensionFilters {
  project_id?: string;
  provider?: string;
  model?: string;
}

export function useOverview() {
  const { start_date, end_date, currency, organizationId } = useFilters();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: ["overview", organizationId, start_date, end_date, currency],
    queryFn: () =>
      api.getOverview({ organization_id: organizationId!, start_date, end_date, currency }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
    refetchInterval,
  });
}

export function useTimeSeries(filters: DimensionFilters = {}) {
  const { start_date, end_date, currency, granularity, organizationId } = useFilters();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: [
      "time-series",
      organizationId,
      start_date,
      end_date,
      currency,
      granularity,
      filters.project_id,
      filters.provider,
      filters.model,
    ],
    queryFn: () =>
      api.getTimeSeries({
        organization_id: organizationId!,
        start_date,
        end_date,
        currency,
        granularity,
        ...filters,
      }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
    refetchInterval,
  });
}

export function useProviders(filters: DimensionFilters = {}) {
  const { start_date, end_date, currency, organizationId } = useFilters();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: [
      "providers",
      organizationId,
      start_date,
      end_date,
      currency,
      filters.project_id,
      filters.provider,
      filters.model,
    ],
    queryFn: () =>
      api.getProviders({
        organization_id: organizationId!,
        start_date,
        end_date,
        currency,
        ...filters,
      }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
    refetchInterval,
  });
}

export function useModels(filters: DimensionFilters = {}) {
  const { start_date, end_date, currency, organizationId } = useFilters();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: [
      "models",
      organizationId,
      start_date,
      end_date,
      currency,
      filters.project_id,
      filters.provider,
      filters.model,
    ],
    queryFn: () =>
      api.getModels({
        organization_id: organizationId!,
        start_date,
        end_date,
        currency,
        ...filters,
      }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
    refetchInterval,
  });
}

export function useProjects(filters: DimensionFilters = {}) {
  const { start_date, end_date, currency, organizationId } = useFilters();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: [
      "projects",
      organizationId,
      start_date,
      end_date,
      currency,
      filters.project_id,
      filters.provider,
      filters.model,
    ],
    queryFn: () =>
      api.getProjects({
        organization_id: organizationId!,
        start_date,
        end_date,
        currency,
        ...filters,
      }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
    refetchInterval,
  });
}

// EP-24.1 — hour-of-day x day-of-week usage heatmap
export function useHeatmap(filters: DimensionFilters = {}) {
  const { start_date, end_date, currency, organizationId } = useFilters();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: [
      "heatmap",
      organizationId,
      start_date,
      end_date,
      currency,
      filters.project_id,
      filters.provider,
      filters.model,
    ],
    queryFn: () =>
      api.getHeatmap({
        organization_id: organizationId!,
        start_date,
        end_date,
        currency,
        ...filters,
      }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
    refetchInterval,
  });
}

// EP-24.1 — real recent-activity feed (imports/syncs/failures), backed by
// GET /v1/dashboard/activity. Distinct from useRecentActivity() below,
// which targets the still-unimplemented raw usage-events endpoint.
export function useActivityFeed(limit = 20) {
  const { organizationId } = useOrgStore();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: ["activity-feed", organizationId, limit],
    queryFn: () => api.getActivityFeed(organizationId!, limit),
    enabled: !!organizationId,
    staleTime: 30 * 1000,
    refetchInterval,
  });
}

export function useOrganization() {
  const { start_date, end_date, currency, organizationId } = useFilters();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: ["organization", organizationId, start_date, end_date, currency],
    queryFn: () =>
      api.getOrganization({ organization_id: organizationId!, start_date, end_date, currency }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
    refetchInterval,
  });
}

export function useRecentActivity(limit = 20) {
  const { organizationId } = useOrgStore();
  const refetchInterval = useRealtimeRefetchInterval(POLL_FALLBACK_MS);
  return useQuery({
    queryKey: ["recent-activity", organizationId, limit],
    queryFn: () => api.getRecentActivity(limit),
    enabled: !!organizationId,
    staleTime: 60 * 1000,
    refetchInterval,
  });
}
