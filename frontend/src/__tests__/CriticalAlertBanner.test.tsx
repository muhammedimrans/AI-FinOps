import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CriticalAlertBanner from "../components/CriticalAlertBanner";
import { useOrgStore } from "../stores/org";
import { useNotificationStore } from "../stores/notifications";
import { useRealtimeStore } from "../realtime/store";
import * as api from "../services/api";
import type { RealtimeEvent } from "../realtime/types";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return { ...actual, getProjects: vi.fn(), getTimeSeries: vi.fn() };
});

const mockedApi = vi.mocked(api);

function budgetExceededEvent(): RealtimeEvent {
  return {
    event_id: "evt_critical",
    timestamp: new Date().toISOString(),
    organization_id: "org_1",
    type: "budget.exceeded",
    version: 1,
    payload: {
      alert_id: "alert_1",
      title: "Prod: budget exceeded",
      message: "Prod has used 110% of its budget this month.",
      severity: "critical",
    },
    trace_id: null,
    correlation_id: null,
  };
}

function renderBanner() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CriticalAlertBanner />
    </QueryClientProvider>,
  );
}

describe("CriticalAlertBanner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    useNotificationStore.setState({ readIds: {}, dismissedIds: {} });
    mockedApi.getProjects.mockResolvedValue({ projects: [] });
    mockedApi.getTimeSeries.mockResolvedValue({
      granularity: "daily",
      start_date: "2026-06-01",
      end_date: "2026-06-30",
      points: [],
      total_cost: "0",
      total_tokens: 0,
      total_requests: 0,
    });
    useRealtimeStore.setState({
      recentActivity: [],
      lastEventByType: {},
      liveMetrics: {
        costDelta: 0,
        tokensDelta: 0,
        requestCount: 0,
        providersSeen: new Set(),
        modelsSeen: new Set(),
      },
    });
  });

  afterEach(() => {
    useOrgStore.setState({ organizationId: null, organizationName: null });
    useNotificationStore.setState({ readIds: {}, dismissedIds: {} });
  });

  it("renders nothing when there are no unread critical alerts", () => {
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a danger-severity unread alert", async () => {
    useRealtimeStore.getState().ingestEvent(budgetExceededEvent());
    renderBanner();
    expect(await screen.findByRole("alert")).toHaveTextContent("Prod: budget exceeded");
  });

  it("does not show an alert once it has been read", () => {
    useRealtimeStore.getState().ingestEvent(budgetExceededEvent());
    useNotificationStore.setState({ readIds: { evt_critical: true }, dismissedIds: {} });
    const { container } = renderBanner();
    expect(container).toBeEmptyDOMElement();
  });

  it("dismisses the banner when Dismiss is clicked", async () => {
    const user = userEvent.setup();
    useRealtimeStore.getState().ingestEvent(budgetExceededEvent());
    renderBanner();
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(useNotificationStore.getState().dismissedIds["evt_critical"]).toBe(true);
  });
});
