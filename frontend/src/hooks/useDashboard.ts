import { useQuery } from "@tanstack/react-query";
import { useUIStore } from "../stores/ui";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";

function useFilters() {
  const { startDate, endDate, currency, granularity } = useUIStore();
  const { organizationId } = useOrgStore();
  return { start_date: startDate, end_date: endDate, currency, granularity, organizationId };
}

export function useOverview() {
  const { start_date, end_date, currency, organizationId } = useFilters();
  return useQuery({
    queryKey: ["overview", organizationId, start_date, end_date, currency],
    queryFn: () =>
      api.getOverview({ organization_id: organizationId!, start_date, end_date, currency }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useTimeSeries() {
  const { start_date, end_date, currency, granularity, organizationId } = useFilters();
  return useQuery({
    queryKey: ["time-series", organizationId, start_date, end_date, currency, granularity],
    queryFn: () =>
      api.getTimeSeries({
        organization_id: organizationId!,
        start_date,
        end_date,
        currency,
        granularity,
      }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useProviders() {
  const { start_date, end_date, currency, organizationId } = useFilters();
  return useQuery({
    queryKey: ["providers", organizationId, start_date, end_date, currency],
    queryFn: () =>
      api.getProviders({ organization_id: organizationId!, start_date, end_date, currency }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useModels() {
  const { start_date, end_date, currency, organizationId } = useFilters();
  return useQuery({
    queryKey: ["models", organizationId, start_date, end_date, currency],
    queryFn: () =>
      api.getModels({ organization_id: organizationId!, start_date, end_date, currency }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useProjects() {
  const { start_date, end_date, currency, organizationId } = useFilters();
  return useQuery({
    queryKey: ["projects", organizationId, start_date, end_date, currency],
    queryFn: () =>
      api.getProjects({ organization_id: organizationId!, start_date, end_date, currency }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useOrganization() {
  const { start_date, end_date, currency, organizationId } = useFilters();
  return useQuery({
    queryKey: ["organization", organizationId, start_date, end_date, currency],
    queryFn: () =>
      api.getOrganization({ organization_id: organizationId!, start_date, end_date, currency }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useRecentActivity(limit = 20) {
  const { organizationId } = useOrgStore();
  return useQuery({
    queryKey: ["recent-activity", organizationId, limit],
    queryFn: () => api.getRecentActivity(limit),
    enabled: !!organizationId,
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  });
}
