import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type { ProviderConnectionRecord } from "../services/api";
import type { OverviewKPIs } from "../types/api";

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

const { GettingStartedBanner } = await import("../features/Overview");

// EP-22.3 — supersedes EP-21.3's 2-item version of this component with the
// full 5-step checklist (Connect Provider / Validate Provider / Create
// Project / Generate AI Usage / View Analytics), all derived from
// useDashboardState() (hooks/useDashboardState.ts) — which itself reuses
// the same provider-connections/projects-crud/overview queries the
// Connections/Projects/Overview pages already populate. No duplicate
// progress state is introduced.

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listProviderConnections: vi.fn(),
    listProjectsCrud: vi.fn(),
    getOverview: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const ZERO_OVERVIEW: OverviewKPIs = {
  total_cost: "0",
  today_cost: "0",
  month_cost: "0",
  total_requests: 0,
  active_models: 0,
  active_providers: 0,
  active_projects: 0,
  total_input_tokens: 0,
  total_output_tokens: 0,
  avg_cost_per_request: "0",
  cost_trend_pct: 0,
  request_trend_pct: 0,
  token_trend_pct: 0,
  currency: "USD",
  period_start: "2020-01-01",
  period_end: "2026-07-01",
};

function connection(overrides: Partial<ProviderConnectionRecord> = {}): ProviderConnectionRecord {
  return {
    id: "conn_1",
    provider_type: "openai",
    display_name: "My OpenAI",
    project_id: null,
    is_active: true,
    has_credential: true,
    masked_api_key: "sk-***AbC",
    base_url: null,
    health_status: "unknown",
    last_validation_status: null,
    last_error: null,
    last_failure_at: null,
    last_recovery_at: null,
    consecutive_failure_count: 0,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

function renderBanner() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <GettingStartedBanner />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GettingStartedBanner (EP-22.3 checklist)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
  });

  it("shows all five steps unchecked for a brand-new organization", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);

    renderBanner();

    expect(await screen.findByText("Getting Started")).toBeTruthy();
    expect(screen.getByText("0 of 5 steps complete")).toBeTruthy();
    expect(screen.getByText("Connect Provider")).toBeTruthy();
    expect(screen.getByText("Validate Provider")).toBeTruthy();
    expect(screen.getByText("Create Project")).toBeTruthy();
    expect(screen.getByText("Generate AI Usage")).toBeTruthy();
    expect(screen.getByText("View Analytics")).toBeTruthy();
  });

  it("checks off Connect Provider once a connection exists", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection()],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);

    renderBanner();

    expect(await screen.findByText("1 of 5 steps complete")).toBeTruthy();
    // A checked step's "Go" link disappears — only unchecked steps link out.
    const validateRow = screen.getByText("Validate Provider").closest("li")!;
    expect(validateRow.querySelector("a")).not.toBeNull();
    const connectRow = screen.getByText("Connect Provider").closest("li")!;
    expect(connectRow.querySelector("a")).toBeNull();
  });

  it("checks off Validate Provider once a connection is healthy", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ last_validation_status: "healthy" })],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);

    renderBanner();

    expect(await screen.findByText("2 of 5 steps complete")).toBeTruthy();
    const validateRow = screen.getByText("Validate Provider").closest("li")!;
    expect(validateRow.querySelector("a")).toBeNull();
  });

  it("checks off Generate AI Usage and View Analytics once usage exists", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ last_validation_status: "healthy" })],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue({ ...ZERO_OVERVIEW, total_requests: 42 });

    renderBanner();

    expect(await screen.findByText("4 of 5 steps complete")).toBeTruthy();
    expect(screen.getByText("Generate AI Usage").closest("li")!.querySelector("a")).toBeNull();
    expect(screen.getByText("View Analytics").closest("li")!.querySelector("a")).toBeNull();
  });

  it("renders nothing once every step is complete", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ last_validation_status: "healthy" })],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({
      projects: [{ id: "proj_1" } as never],
      total: 1,
    });
    mockedApi.getOverview.mockResolvedValue({ ...ZERO_OVERVIEW, total_requests: 42 });

    const { container } = renderBanner();
    await waitFor(() => expect(mockedApi.listProviderConnections).toHaveBeenCalled());
    await waitFor(() => expect(mockedApi.listProjectsCrud).toHaveBeenCalled());
    await waitFor(() => expect(mockedApi.getOverview).toHaveBeenCalled());
    await waitFor(() => expect(container.textContent).toBe(""));
  });
});
