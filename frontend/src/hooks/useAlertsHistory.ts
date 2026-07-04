import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type { AlertApiSeverity, AlertApiStatus } from "../services/api";

export interface AlertHistoryFilters {
  status?: AlertApiStatus;
  severity?: AlertApiSeverity;
  alertType?: string;
  search?: string;
}

const QUERY_KEY = "alerts-history";

/**
 * Persisted alert history — backs the notification center's search/filter
 * surface. Distinct from `useAlerts()` (client-derived + live-merged, used
 * for the bell dropdown's instant feed): this hook calls `GET /v1/alerts`
 * directly, which only returns alert types the backend actually persists
 * (budget/membership/API-key triggers as of EP-19.3 — see
 * backend/docs/realtime/ALERT_ARCHITECTURE.md).
 */
export function useAlertsHistory(filters: AlertHistoryFilters = {}) {
  const { organizationId } = useOrgStore();
  return useQuery({
    queryKey: [QUERY_KEY, organizationId, filters],
    queryFn: () =>
      api.listAlerts({
        organizationId: organizationId!,
        ...(filters.status !== undefined && { status: filters.status }),
        ...(filters.severity !== undefined && { severity: filters.severity }),
        ...(filters.alertType !== undefined && { alertType: filters.alertType }),
        ...(filters.search !== undefined && { search: filters.search }),
        limit: 100,
      }),
    enabled: !!organizationId,
  });
}

/** Acknowledge/resolve/dismiss/reopen — each invalidates the history query
 * so the notification center reflects the new status immediately, in
 * addition to whatever live WebSocket event the backend also publishes. */
export function useAlertActions() {
  const { organizationId } = useOrgStore();
  const queryClient = useQueryClient();

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: [QUERY_KEY, organizationId] });

  const acknowledge = useMutation({
    mutationFn: (vars: { alertId: string; reason?: string }) =>
      api.acknowledgeAlert(organizationId!, vars.alertId, vars.reason),
    onSuccess: invalidate,
  });

  const resolve = useMutation({
    mutationFn: (alertId: string) => api.resolveAlert(organizationId!, alertId),
    onSuccess: invalidate,
  });

  const archive = useMutation({
    mutationFn: (alertId: string) => api.dismissAlert(organizationId!, alertId),
    onSuccess: invalidate,
  });

  const reopen = useMutation({
    mutationFn: (alertId: string) => api.reopenAlert(organizationId!, alertId),
    onSuccess: invalidate,
  });

  return { acknowledge, resolve, archive, reopen };
}
