import { useQuery } from "@tanstack/react-query";
import { useUIStore } from "../stores/ui";
import * as api from "../lib/api";

function useFilters() {
  const { startDate, endDate, currency, granularity } = useUIStore();
  return { start_date: startDate, end_date: endDate, currency, granularity };
}

export function useOverview() {
  const { start_date, end_date, currency } = useFilters();
  return useQuery({
    queryKey: ["overview", start_date, end_date, currency],
    queryFn: () => api.getOverview({ start_date, end_date, currency }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useTimeSeries() {
  const { start_date, end_date, currency, granularity } = useFilters();
  return useQuery({
    queryKey: ["time-series", start_date, end_date, currency, granularity],
    queryFn: () => api.getTimeSeries({ start_date, end_date, currency, granularity }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useProviders() {
  const { start_date, end_date, currency } = useFilters();
  return useQuery({
    queryKey: ["providers", start_date, end_date, currency],
    queryFn: () => api.getProviders({ start_date, end_date, currency }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useModels() {
  const { start_date, end_date, currency } = useFilters();
  return useQuery({
    queryKey: ["models", start_date, end_date, currency],
    queryFn: () => api.getModels({ start_date, end_date, currency }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useProjects() {
  const { start_date, end_date, currency } = useFilters();
  return useQuery({
    queryKey: ["projects", start_date, end_date, currency],
    queryFn: () => api.getProjects({ start_date, end_date, currency }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useOrganization() {
  const { start_date, end_date, currency } = useFilters();
  return useQuery({
    queryKey: ["organization", start_date, end_date, currency],
    queryFn: () => api.getOrganization({ start_date, end_date, currency }),
    staleTime: 5 * 60 * 1000,
  });
}

export function useRecentActivity(limit = 20) {
  return useQuery({
    queryKey: ["recent-activity", limit],
    queryFn: () => api.getRecentActivity(limit),
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  });
}
