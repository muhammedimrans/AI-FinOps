import { useQuery } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import { listProviderConnections, listProjectsCrud, getOverview } from "../services/api";
import { getToday } from "../utils";
import { hasKnownUsageApi } from "../lib/providerCatalog";

// EP-22.3 — Intelligent Dashboard Empty States.
//
// Reuses three existing endpoints (provider connections, projects, and the
// dashboard overview) rather than introducing a dedicated summary endpoint
// — per this EP's own "avoid new endpoints unless absolutely required"
// instruction, the three signals below are cheap, already-cached (the
// provider-connections and projects-crud queries share their query keys
// with features/Connections.tsx and features/Projects.tsx, exactly like
// the EP-21.3 GettingStartedBanner this hook supersedes) and sufficient to
// derive every state this EP's dashboard state machine needs.
//
// "Has this organization ever recorded any usage" has no dedicated
// endpoint and doesn't need one: the existing GET /v1/dashboard/overview
// already answers "how much usage occurred in [start, end]" — querying it
// with a fixed, far-past start date (predating the product's own
// existence) turns it into an honest all-time check without adding any
// new backend surface area.
const ALL_TIME_START = "2020-01-01";

export type DashboardSetupState = 1 | 2 | 3 | 4;

export interface DashboardProgress {
  isLoading: boolean;
  hasConnections: boolean;
  /** Real connection count — EP-25.4.4's Workspace Ready card shows this
   * directly rather than just the boolean above. */
  connectionsCount: number;
  hasValidatedConnection: boolean;
  hasProjects: boolean;
  /** Real project count — see `connectionsCount`. */
  projectsCount: number;
  hasUsage: boolean;
  /**
   * True when at least one *validated* connection is for a provider that
   * actually exposes a bulk usage-history API (`hasKnownUsageApi`, mirrors
   * the backend's `_KNOWN_USAGE_API_PROVIDERS` — EP-24.3/26.0.1). False for
   * an org whose only validated connections are to usage-incapable
   * providers (Google/Azure/Grok/Ollama today) — for those orgs, state 3
   * ("waiting for usage") will never resolve to state 4 no matter how long
   * you wait, since there's nothing for the sync pipeline to import. This
   * signal is what lets the UI say so honestly instead of implying usage
   * is merely delayed (EP-26.0.3.2).
   */
  hasUsageCapableConnection: boolean;
  /**
   * 1 — no provider connected yet
   * 2 — a provider exists, but none has a successful validation
   * 3 — a provider is validated, but no usage has ever been recorded
   * 4 — usage exists; render the full dashboard
   */
  state: DashboardSetupState;
}

export function useDashboardState(): DashboardProgress {
  const organizationId = useOrgStore((s) => s.organizationId);

  const connections = useQuery({
    queryKey: ["provider-connections", organizationId],
    queryFn: () => listProviderConnections(organizationId!),
    enabled: !!organizationId,
  });
  const projects = useQuery({
    queryKey: ["projects-crud", organizationId],
    queryFn: () => listProjectsCrud(organizationId!),
    enabled: !!organizationId,
  });
  // Distinct query key from the date-range-scoped "overview" query
  // features/Overview.tsx's KPI cards use — this one is intentionally
  // date-range-independent (all-time) and only used for state detection.
  const allTimeUsage = useQuery({
    queryKey: ["overview-all-time", organizationId],
    queryFn: () =>
      getOverview({
        organization_id: organizationId!,
        start_date: ALL_TIME_START,
        end_date: getToday(),
      }),
    enabled: !!organizationId,
    staleTime: 5 * 60 * 1000,
  });

  const isLoading = connections.isLoading || projects.isLoading || allTimeUsage.isLoading;
  const hasConnections = (connections.data?.total ?? 0) > 0;
  const hasValidatedConnection = (connections.data?.connections ?? []).some(
    (c) => c.last_validation_status === "healthy",
  );
  const hasProjects = (projects.data?.total ?? 0) > 0;
  const hasUsage = (allTimeUsage.data?.total_requests ?? 0) > 0;
  const hasUsageCapableConnection = (connections.data?.connections ?? []).some(
    (c) => c.last_validation_status === "healthy" && hasKnownUsageApi(c.provider_type),
  );

  const state: DashboardSetupState = !hasConnections
    ? 1
    : !hasValidatedConnection
      ? 2
      : !hasUsage
        ? 3
        : 4;

  return {
    isLoading,
    hasConnections,
    connectionsCount: connections.data?.total ?? 0,
    hasValidatedConnection,
    hasProjects,
    projectsCount: projects.data?.total ?? 0,
    hasUsage,
    hasUsageCapableConnection,
    state,
  };
}
