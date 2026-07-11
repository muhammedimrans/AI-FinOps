import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import { useOnboardingWidgetStore } from "../stores/onboardingWidget";
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

const { OnboardingWidget } = await import("../features/Overview");

// EP-25.4.4 — supersedes EP-22.3's GettingStartedBanner test suite. The
// checklist itself is unchanged (Connect Provider / Validate Provider /
// Create Project / Generate AI Usage), but "View Analytics" is now a real,
// independently-tracked signal (has the user opened /analytics — Part 2),
// and completing every step now renders a "Workspace Ready" card (Part 1/7)
// instead of rendering nothing, with Dismiss/Never-show-again controls
// while incomplete (Part 1).

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

function renderWidget(props: { kpi?: OverviewKPIs; lastSyncAt?: string | null } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OnboardingWidget kpi={props.kpi} lastSyncAt={props.lastSyncAt ?? null} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OnboardingWidget (EP-25.4.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    useOnboardingWidgetStore.setState({ neverShow: false, dismissed: false, visitedAnalytics: false });
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
  });

  it("shows all five steps unchecked for a brand-new organization", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);

    renderWidget();

    expect(await screen.findByText("Getting Started")).toBeTruthy();
    expect(screen.getByText("0 of 5 steps complete")).toBeTruthy();
    expect(screen.getByText("Connect Provider")).toBeTruthy();
    expect(screen.getByText("Validate Provider")).toBeTruthy();
    expect(screen.getByText("Create Project")).toBeTruthy();
    expect(screen.getByText("Generate AI Usage")).toBeTruthy();
    expect(screen.getByText("View Analytics")).toBeTruthy();
  });

  it("checks off Connect Provider once a connection exists", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [connection()], total: 1 });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);

    renderWidget();

    expect(await screen.findByText("1 of 5 steps complete")).toBeTruthy();
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

    renderWidget();

    expect(await screen.findByText("2 of 5 steps complete")).toBeTruthy();
    const validateRow = screen.getByText("Validate Provider").closest("li")!;
    expect(validateRow.querySelector("a")).toBeNull();
  });

  it("checks off Generate AI Usage once usage exists, independent of View Analytics", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ last_validation_status: "healthy" })],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue({ ...ZERO_OVERVIEW, total_requests: 42 });

    renderWidget();

    expect(await screen.findByText("3 of 5 steps complete")).toBeTruthy();
    expect(screen.getByText("Generate AI Usage").closest("li")!.querySelector("a")).toBeNull();
    // View Analytics is a separate, real signal — not auto-completed by usage existing.
    expect(screen.getByText("View Analytics").closest("li")!.querySelector("a")).not.toBeNull();
  });

  it("checks off View Analytics once the user has actually visited Analytics", async () => {
    useOnboardingWidgetStore.setState({ visitedAnalytics: true });
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);

    renderWidget();

    expect(await screen.findByText("1 of 5 steps complete")).toBeTruthy();
    expect(screen.getByText("View Analytics").closest("li")!.querySelector("a")).toBeNull();
  });

  // EP-26.0.3.2 — a validated Google (or other usage-incapable) connection
  // must not leave "Generate AI Usage" looking like a stuck todo with no
  // explanation — it should disclose why, and its "Go" link (to a page
  // that will never resolve the item) should be hidden.
  it("shows an honest note with a Playground link instead of a dead-end 'Go' link for Generate AI Usage when the only validated connection has no usage API", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ provider_type: "google", last_validation_status: "healthy" })],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);

    renderWidget();

    expect(await screen.findByText("2 of 5 steps complete")).toBeTruthy();
    expect(screen.getAllByText(/doesn't expose historical usage/i).length).toBe(1);
    const usageRow = screen.getByText("Generate AI Usage").closest("li")!;
    const link = usageRow.querySelector("a");
    expect(link).not.toBeNull();
    expect(link).toHaveTextContent("Playground");
    expect(link).toHaveAttribute("href", "/playground");
    // View Analytics is unaffected by the usage-incapable-provider note.
    expect(screen.getByText("View Analytics").closest("li")!.querySelector("a")).not.toBeNull();
  });

  it("renders the Workspace Ready card once every step (including View Analytics) is complete", async () => {
    useOnboardingWidgetStore.setState({ visitedAnalytics: true });
    mockedApi.listProviderConnections.mockResolvedValue({
      connections: [connection({ last_validation_status: "healthy" })],
      total: 1,
    });
    mockedApi.listProjectsCrud.mockResolvedValue({
      projects: [{ id: "proj_1" } as never],
      total: 1,
    });
    mockedApi.getOverview.mockResolvedValue({
      ...ZERO_OVERVIEW,
      total_requests: 42,
      today_cost: "12.50",
      active_models: 3,
    });

    renderWidget({
      kpi: { ...ZERO_OVERVIEW, total_requests: 42, today_cost: "12.50", active_models: 3 },
      lastSyncAt: "2026-07-01T12:00:00Z",
    });

    expect(await screen.findByText("Workspace Ready")).toBeTruthy();
    expect(screen.queryByText("Getting Started")).not.toBeInTheDocument();
    expect(screen.getByText("Providers Connected")).toBeTruthy();
    expect(screen.getByText("Models")).toBeTruthy();
    expect(screen.getByText("Today's Usage")).toBeTruthy();
    expect(screen.getByRole("link", { name: /open playground/i })).toHaveAttribute("href", "/playground");
    expect(screen.getByRole("link", { name: "Analytics" })).toHaveAttribute("href", "/analytics");
    expect(screen.getByRole("link", { name: "Connections" })).toHaveAttribute("href", "/connections");
  });

  it("Dismiss hides the checklist for the rest of this session", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);
    const user = userEvent.setup();

    const { container } = renderWidget();
    await screen.findByText("Getting Started");
    await user.click(screen.getByLabelText("Dismiss"));
    await waitFor(() => expect(container.textContent).toBe(""));
  });

  it("Never show again hides the widget, surviving even a completed setup, until reset", async () => {
    mockedApi.listProviderConnections.mockResolvedValue({ connections: [], total: 0 });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
    mockedApi.getOverview.mockResolvedValue(ZERO_OVERVIEW);
    const user = userEvent.setup();

    const { container } = renderWidget();
    await screen.findByText("Getting Started");
    await user.click(screen.getByLabelText("Never show this again"));
    await waitFor(() => expect(container.textContent).toBe(""));
    expect(useOnboardingWidgetStore.getState().neverShow).toBe(true);

    useOnboardingWidgetStore.getState().reset();
    expect(useOnboardingWidgetStore.getState().neverShow).toBe(false);
  });
});
