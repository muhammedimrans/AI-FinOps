import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type {
  OverviewKPIs,
  TimeSeriesResponse,
  ProvidersResponse,
  ModelsResponse,
  ActivityFeed,
} from "../types/api";
import type { ProviderConnectionRecord } from "../services/api";

// features/Overview.tsx transitively imports the theme store (via
// lib/chartPalette), which reads window.matchMedia on first access —
// jsdom doesn't implement it, so stub it before that import runs.
if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });
}

// EP-24.1 — component tests for Overview.tsx: the 8 top-level KPI cards
// (Total Spend / Today's Spend / This Month / Total Tokens / Total
// Requests / Active Providers / Projects / Avg Cost per Request) and the
// real Recent Activity section (imports/syncs/failures), replacing the
// prior 4-card layout and the placeholder-only activity feed.

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listProviderConnections: vi.fn(),
    listProjectsCrud: vi.fn(),
    getOverview: vi.fn(),
    getTimeSeries: vi.fn(),
    getProviders: vi.fn(),
    getModels: vi.fn(),
    getActivityFeed: vi.fn(),
    getRecentActivity: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const FULL_OVERVIEW: OverviewKPIs = {
  total_cost: "1234.56",
  today_cost: "12.34",
  month_cost: "567.89",
  total_requests: 4200,
  active_models: 6,
  active_providers: 3,
  active_projects: 5,
  total_input_tokens: 700000,
  total_output_tokens: 300000,
  avg_cost_per_request: "0.294",
  cost_trend_pct: 8.2,
  request_trend_pct: -1.1,
  token_trend_pct: 4.4,
  currency: "USD",
  period_start: "2026-06-01",
  period_end: "2026-07-10",
};

const EMPTY_TIME_SERIES: TimeSeriesResponse = { data: [], granularity: "daily", currency: "USD" };
const EMPTY_PROVIDERS: ProvidersResponse = { providers: [], currency: "USD" };
const EMPTY_MODELS: ModelsResponse = { models: [], currency: "USD" };
const EMPTY_ACTIVITY: ActivityFeed = { imports: [], syncs: [], failures: [] };

function connection(): ProviderConnectionRecord {
  return {
    id: "conn_1",
    provider_type: "openai",
    display_name: "My OpenAI",
    project_id: null,
    is_active: true,
    has_credential: true,
    masked_api_key: "sk-***AbC",
    base_url: null,
    health_status: "healthy",
    last_validation_status: "healthy",
    last_error: null,
    last_failure_at: null,
    last_recovery_at: null,
    consecutive_failure_count: 0,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
  };
}

function mockDashboardState() {
  mockedApi.listProviderConnections.mockResolvedValue({ connections: [connection()], total: 1 });
  mockedApi.listProjectsCrud.mockResolvedValue({ projects: [{ id: "proj_1" } as never], total: 1 });
  // LiveActivityFeed's own useRecentActivity() hook — unrelated to EP-24.1's
  // useActivityFeed(), given a default so it doesn't warn about undefined data.
  mockedApi.getRecentActivity.mockResolvedValue({ events: [], total: 0, page: 1, page_size: 10 });
}

async function renderOverview() {
  const { default: Overview } = await import("../features/Overview");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Overview />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Overview (EP-24.1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
  });

  it("renders all 8 top-level KPI cards", async () => {
    mockDashboardState();
    mockedApi.getOverview.mockResolvedValue(FULL_OVERVIEW);
    mockedApi.getTimeSeries.mockResolvedValue(EMPTY_TIME_SERIES);
    mockedApi.getProviders.mockResolvedValue(EMPTY_PROVIDERS);
    mockedApi.getModels.mockResolvedValue(EMPTY_MODELS);
    mockedApi.getActivityFeed.mockResolvedValue(EMPTY_ACTIVITY);

    await renderOverview();

    expect(await screen.findByText("Total Spend")).toBeTruthy();
    expect(screen.getByText("Today's Spend")).toBeTruthy();
    expect(screen.getByText("This Month")).toBeTruthy();
    expect(screen.getByText("Total Tokens")).toBeTruthy();
    expect(screen.getByText("Total Requests")).toBeTruthy();
    expect(screen.getByText("Active Providers")).toBeTruthy();
    expect(screen.getByText("Projects")).toBeTruthy();
    expect(screen.getByText("Avg Cost / Request")).toBeTruthy();
  });

  it("shows real today/month spend values, not zeroed placeholders", async () => {
    mockDashboardState();
    mockedApi.getOverview.mockResolvedValue(FULL_OVERVIEW);
    mockedApi.getTimeSeries.mockResolvedValue(EMPTY_TIME_SERIES);
    mockedApi.getProviders.mockResolvedValue(EMPTY_PROVIDERS);
    mockedApi.getModels.mockResolvedValue(EMPTY_MODELS);
    mockedApi.getActivityFeed.mockResolvedValue(EMPTY_ACTIVITY);

    await renderOverview();

    expect(await screen.findByText("$12.34")).toBeTruthy();
    expect(screen.getByText("$567.89")).toBeTruthy();
  });

  it("renders Recent Activity with real imports/syncs/failures once usage exists", async () => {
    mockDashboardState();
    mockedApi.getOverview.mockResolvedValue(FULL_OVERVIEW);
    mockedApi.getTimeSeries.mockResolvedValue(EMPTY_TIME_SERIES);
    mockedApi.getProviders.mockResolvedValue(EMPTY_PROVIDERS);
    mockedApi.getModels.mockResolvedValue(EMPTY_MODELS);
    mockedApi.getActivityFeed.mockResolvedValue({
      imports: [
        {
          id: "run_1",
          provider: "openai",
          status: "completed",
          triggeredBy: "manual",
          startedAt: "2026-07-10T10:00:00Z",
          completedAt: "2026-07-10T10:01:00Z",
          eventsCollected: 15,
          errorMessage: null,
        },
      ],
      syncs: [],
      failures: [
        {
          connectionId: "conn_2",
          providerType: "anthropic",
          displayName: "Prod Anthropic",
          lastError: "The API key is invalid or has been revoked.",
          lastFailureAt: "2026-07-10T09:00:00Z",
          consecutiveFailureCount: 2,
        },
      ],
    });

    await renderOverview();

    expect(await screen.findByText("Sync Activity")).toBeTruthy();
    expect(screen.getByText("Latest Imports")).toBeTruthy();
    expect(screen.getByText("Latest Syncs")).toBeTruthy();
    expect(screen.getByText("Provider Failures")).toBeTruthy();
    expect(screen.getByText("Prod Anthropic")).toBeTruthy();
    expect(screen.getByText("The API key is invalid or has been revoked.")).toBeTruthy();
  });
});
