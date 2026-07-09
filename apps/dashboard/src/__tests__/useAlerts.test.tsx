import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAlerts } from "../hooks/useAlerts";
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

function orgUpdatedEvent(overrides: Partial<RealtimeEvent> = {}): RealtimeEvent {
  return {
    event_id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    organization_id: "org_1",
    type: "organization.updated",
    version: 1,
    payload: {
      alert_id: "alert_abc123",
      alert_type: "org_member_added",
      severity: "info",
      status: "open",
      title: "acme@example.com joined the organization",
      message: "acme@example.com was added as member.",
      occurrence_count: 1,
    },
    trace_id: null,
    correlation_id: null,
    ...overrides,
  };
}

/** Renders the alerts as a simple list so we can assert on the hook's
 * output without a full notification-panel component in the loop. */
function Harness() {
  const { alerts, unreadCount } = useAlerts();
  return (
    <div>
      <p data-testid="unread-count">{unreadCount}</p>
      <ul>
        {alerts.map((a) => (
          <li key={a.id} data-testid="alert-row" data-severity={a.severity} data-alert-id={a.alertId ?? ""}>
            {a.title}
          </li>
        ))}
      </ul>
    </div>
  );
}

function renderHarness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  );
}

describe("useAlerts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    useNotificationStore.setState({ readIds: {}, dismissedIds: {} });
    mockedApi.getProjects.mockResolvedValue({ projects: [], currency: "USD" });
    mockedApi.getTimeSeries.mockResolvedValue({
      granularity: "daily",
      currency: "USD",
      data: [],
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

  it("shows no alerts when there is no data and no live events", async () => {
    renderHarness();
    expect(await screen.findByTestId("unread-count")).toHaveTextContent("0");
    expect(screen.queryAllByTestId("alert-row")).toHaveLength(0);
  });

  it("derives a budget alert when a project is over budget", async () => {
    mockedApi.getProjects.mockResolvedValue({
      projects: [
        {
          project_id: "proj_1",
          project_name: "Prod",
          team: "platform",
          total_cost: "150",
          budget: "100",
          budget_utilization_pct: 150,
          request_count: 0,
          top_models: [],
          cost_trend: 0,
          trend_data: [],
        },
      ],
      currency: "USD",
    });
    renderHarness();
    expect(await screen.findByText(/over budget/i)).toBeInTheDocument();
  });

  it("merges a live-fired alert and threads through its backend alert_id", async () => {
    useRealtimeStore.getState().ingestEvent(orgUpdatedEvent());
    renderHarness();
    const row = await screen.findByText("acme@example.com joined the organization");
    expect(row).toHaveAttribute("data-alert-id", "alert_abc123");
    expect(row).toHaveAttribute("data-severity", "info");
  });

  it("prefers the alert's own severity over the generic event-type default", async () => {
    // organization.updated defaults to "info" in EVENT_COPY, but a critical
    // payload severity must win — this is how a critical budget/API-key
    // alert riding the same event type still shows as danger in the UI.
    useRealtimeStore.getState().ingestEvent(
      orgUpdatedEvent({
        payload: {
          alert_id: "alert_xyz",
          title: "Something critical happened",
          message: "critical",
          severity: "critical",
        },
      }),
    );
    renderHarness();
    const row = await screen.findByText("Something critical happened");
    expect(row).toHaveAttribute("data-severity", "danger");
  });

  it("excludes dismissed alerts and reflects read state", async () => {
    useRealtimeStore.getState().ingestEvent(orgUpdatedEvent({ event_id: "evt_1" }));
    useNotificationStore.setState({ readIds: {}, dismissedIds: { evt_1: true } });
    renderHarness();
    expect(await screen.findByTestId("unread-count")).toHaveTextContent("0");
    expect(screen.queryByText("acme@example.com joined the organization")).not.toBeInTheDocument();
  });

  it("does not surface unrelated live event types (e.g. usage.created) as alerts", async () => {
    act(() => {
      useRealtimeStore.getState().ingestEvent({
        event_id: "evt_usage",
        timestamp: new Date().toISOString(),
        organization_id: "org_1",
        type: "usage.created",
        version: 1,
        payload: { provider: "openai", model: "gpt-4", cost: "1", currency: "USD", total_tokens: 1, status: "success", project_id: null },
        trace_id: null,
        correlation_id: null,
      });
    });
    renderHarness();
    expect(await screen.findByTestId("unread-count")).toHaveTextContent("0");
  });
});
