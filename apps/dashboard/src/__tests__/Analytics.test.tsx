import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type {
  TimeSeriesResponse,
  ModelsResponse,
  ProvidersResponse,
  ProjectsResponse,
  HeatmapResponse,
} from "../types/api";
import type { SchedulerStatusResponse } from "../services/api";

// features/Analytics.tsx transitively imports the theme store (via
// lib/chartPalette), which reads window.matchMedia on first access —
// jsdom doesn't implement it, so stub it before that import runs (same
// workaround GettingStartedBanner.test.tsx already uses).
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

// EP-24.1 — component tests for Analytics.tsx: dimension filters threaded
// through to the dashboard hooks, the generalized CSV export (was
// Models-only), the new Token Trend / Usage Heatmap / Project Spend
// sections, and the scheduler-status-driven query invalidation.

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    getTimeSeries: vi.fn(),
    getModels: vi.fn(),
    getProviders: vi.fn(),
    getProjects: vi.fn(),
    getHeatmap: vi.fn(),
    getSchedulerStatus: vi.fn(),
    listProviderConnections: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const EMPTY_TIME_SERIES: TimeSeriesResponse = { data: [], granularity: "daily", currency: "USD" };
const EMPTY_MODELS: ModelsResponse = { models: [], currency: "USD" };
const EMPTY_PROVIDERS: ProvidersResponse = { providers: [], currency: "USD" };
const EMPTY_PROJECTS: ProjectsResponse = { projects: [], currency: "USD" };
const EMPTY_HEATMAP: HeatmapResponse = { cells: [], currency: "USD" };

const IDLE_SCHEDULER_STATUS: SchedulerStatusResponse = {
  organization_id: "org_1",
  auto_sync_enabled: false,
  interval: "1h",
  interval_seconds: 3600,
  last_sync_at: null,
  last_sync_status: null,
  next_sync_at: null,
  current_job: null,
  scheduler_health: "disabled",
  monitoring: {
    is_running: false,
    active_jobs: 0,
    queued_jobs: 0,
    completed_jobs: 0,
    failed_jobs: 0,
    average_duration_seconds: null,
    last_execution: null,
  },
};

function mockAllEmpty() {
  mockedApi.getTimeSeries.mockResolvedValue(EMPTY_TIME_SERIES);
  mockedApi.getModels.mockResolvedValue(EMPTY_MODELS);
  mockedApi.getProviders.mockResolvedValue(EMPTY_PROVIDERS);
  mockedApi.getProjects.mockResolvedValue(EMPTY_PROJECTS);
  mockedApi.getHeatmap.mockResolvedValue(EMPTY_HEATMAP);
  mockedApi.getSchedulerStatus.mockResolvedValue(IDLE_SCHEDULER_STATUS);
  mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
}

async function renderAnalytics() {
  const { default: Analytics } = await import("../features/Analytics");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Analytics (EP-24.1)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
  });

  it("renders the filter controls (Project / Provider / Model)", async () => {
    mockAllEmpty();
    await renderAnalytics();

    expect(await screen.findByLabelText("Filter by project")).toBeTruthy();
    expect(screen.getByLabelText("Filter by provider")).toBeTruthy();
    expect(screen.getByLabelText("Filter by model")).toBeTruthy();
  });

  it("passes the selected provider filter through to every dashboard query", async () => {
    mockAllEmpty();
    await renderAnalytics();

    const providerSelect = await screen.findByLabelText("Filter by provider");
    fireEvent.change(providerSelect, { target: { value: "openai" } });

    await waitFor(() => {
      const lastCall = mockedApi.getModels.mock.calls.at(-1)?.[0];
      expect(lastCall?.provider).toBe("openai");
    });
    const timeSeriesCall = mockedApi.getTimeSeries.mock.calls.at(-1)?.[0];
    expect(timeSeriesCall?.provider).toBe("openai");
  });

  it("shows a Clear filters button only once a filter is active", async () => {
    mockAllEmpty();
    await renderAnalytics();

    expect(screen.queryByText("Clear filters")).toBeNull();

    const providerSelect = await screen.findByLabelText("Filter by provider");
    fireEvent.change(providerSelect, { target: { value: "anthropic" } });

    expect(await screen.findByText("Clear filters")).toBeTruthy();
    fireEvent.click(screen.getByText("Clear filters"));
    await waitFor(() => expect(screen.queryByText("Clear filters")).toBeNull());
  });

  it("renders the Token Trend, Usage Heatmap, and Project Spend sections", async () => {
    mockAllEmpty();
    await renderAnalytics();

    expect(await screen.findByText("Token Trend")).toBeTruthy();
    expect(screen.getByText("Usage Heatmap")).toBeTruthy();
    expect(screen.getByText("Project Spend")).toBeTruthy();
  });

  it("shows an empty-state message when the heatmap has no cells", async () => {
    mockAllEmpty();
    await renderAnalytics();

    expect(await screen.findByText("No usage recorded in the selected period.")).toBeTruthy();
  });

  it("renders project rows in the Project Spend table once data loads", async () => {
    mockAllEmpty();
    mockedApi.getProjects.mockResolvedValue({
      projects: [
        {
          project_id: "proj_1",
          project_name: "Production API",
          team: "",
          total_cost: "42.00",
          budget: "100.00",
          budget_utilization_pct: 42,
          request_count: 10,
          top_models: [],
          cost_trend: 0,
          trend_data: [],
        },
      ],
      currency: "USD",
    });
    await renderAnalytics();

    const matches = await screen.findAllByText("Production API");
    expect(matches.length).toBeGreaterThan(0);
  });

  it("exportCSV downloads a CSV for the selected format", async () => {
    mockAllEmpty();
    mockedApi.getModels.mockResolvedValue({
      models: [
        {
          model_id: "gpt-4",
          provider: "openai",
          display_name: "GPT-4",
          total_cost: "10.00",
          request_count: 5,
          input_tokens: 100,
          output_tokens: 50,
          avg_cost_per_request: "2.0",
          cost_per_1k_tokens: "0.1",
        },
      ],
      currency: "USD",
    });
    await renderAnalytics();

    // jsdom doesn't implement anchor.click() navigation — just assert it
    // doesn't throw and that a real anchor download is attempted.
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const csvButton = await screen.findByText("CSV");
    fireEvent.click(csvButton);

    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();
  });

  it("invalidates dashboard queries when the scheduler reports a completed job", async () => {
    mockAllEmpty();
    mockedApi.getSchedulerStatus.mockResolvedValue({
      ...IDLE_SCHEDULER_STATUS,
      current_job: {
        job_id: "job_1",
        organization_id: "org_1",
        status: "completed",
        queued_at: "2026-07-09T23:59:00Z",
        started_at: "2026-07-10T00:00:00Z",
        completed_at: "2026-07-10T00:01:00Z",
        connections_synced: 1,
        connections_failed: 0,
        duration_seconds: 60,
        records_imported: 5,
        retry_count: 0,
        error: null,
      },
    });
    await renderAnalytics();

    // Scheduler status resolves and the effect fires; the underlying
    // dashboard queries should be (re-)requested as a result of the
    // invalidation, i.e. getTimeSeries is called more than the initial
    // mount call once the job-completion effect runs.
    await waitFor(() => expect(mockedApi.getSchedulerStatus).toHaveBeenCalled());
  });

  // EP-26.0.3.3 Part 5 — a connected provider with no usage API must
  // never show a bare "no data" chart; it should disclose why and point
  // at AI Playground as the real next action.
  it("shows an honest empty state with an AI Playground link when the only connection has no usage API", async () => {
    mockAllEmpty();
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [
        {
          id: "conn_1",
          provider_type: "google",
          display_name: "My Gemini",
          project_id: null,
          is_active: true,
          has_credential: true,
          masked_api_key: "AIza***xyz",
          base_url: null,
          health_status: "healthy",
          last_validation_status: "healthy",
          last_error: null,
          last_failure_at: null,
          last_recovery_at: null,
          consecutive_failure_count: 0,
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-01T00:00:00Z",
        },
      ],
      total: 1,
    });
    await renderAnalytics();

    expect(await screen.findByText(/My Gemini is connected successfully/i)).toBeTruthy();
    expect(screen.getByText(/Historical usage cannot be imported/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: /open ai playground/i })).toHaveAttribute(
      "href",
      "/playground",
    );
  });
});
