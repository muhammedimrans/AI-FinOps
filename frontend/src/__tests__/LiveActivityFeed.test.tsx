import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LiveActivityFeed from "../components/LiveActivityFeed";
import { useOrgStore } from "../stores/org";
import { useRealtimeStore } from "../realtime/store";
import * as api from "../services/api";
import type { RealtimeEvent } from "../realtime/types";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return { ...actual, getRecentActivity: vi.fn() };
});

const mockedApi = vi.mocked(api);

function usageEvent(overrides: Partial<RealtimeEvent> = {}): RealtimeEvent {
  return {
    event_id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    organization_id: "org_1",
    type: "usage.created",
    version: 1,
    payload: { provider: "openai", model: "gpt-4.1", cost: "0.42", currency: "USD", total_tokens: 100, status: "success", project_id: null },
    trace_id: null,
    correlation_id: null,
    ...overrides,
  };
}

function renderFeed() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LiveActivityFeed limit={10} />
    </QueryClientProvider>,
  );
}

describe("LiveActivityFeed", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.getRecentActivity.mockResolvedValue({ events: [], total: 0, page: 1, page_size: 10 });
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
  });

  it("shows an empty state when there is no activity yet", async () => {
    renderFeed();
    expect(await screen.findByText(/no activity yet/i)).toBeInTheDocument();
  });

  it("renders a live usage.created event as a row, newest first", async () => {
    useRealtimeStore.getState().ingestEvent(usageEvent());
    renderFeed();
    expect(await screen.findByText("gpt-4.1")).toBeInTheDocument();
  });

  it("shows newer events above older ones", async () => {
    useRealtimeStore.getState().ingestEvent(usageEvent({ payload: { provider: "openai", model: "old-model", cost: "1", currency: "USD", total_tokens: 1, status: "success", project_id: null } }));
    useRealtimeStore.getState().ingestEvent(usageEvent({ payload: { provider: "openai", model: "new-model", cost: "1", currency: "USD", total_tokens: 1, status: "success", project_id: null } }));
    renderFeed();
    const rows = await screen.findAllByRole("row");
    // rows[0] is the header row
    expect(rows[1]).toHaveTextContent("new-model");
    expect(rows[2]).toHaveTextContent("old-model");
  });

  it("pauses updates while the pointer is hovering the list", async () => {
    const user = userEvent.setup();
    useRealtimeStore.getState().ingestEvent(
      usageEvent({ payload: { provider: "openai", model: "first-model", cost: "1", currency: "USD", total_tokens: 1, status: "success", project_id: null } }),
    );
    renderFeed();
    expect(await screen.findByText("first-model")).toBeInTheDocument();

    const table = screen.getByRole("table");
    await user.hover(table);

    act(() => {
      useRealtimeStore.getState().ingestEvent(
        usageEvent({ payload: { provider: "openai", model: "second-model", cost: "1", currency: "USD", total_tokens: 1, status: "success", project_id: null } }),
      );
    });
    // While paused, the newly arrived event must not appear yet.
    expect(screen.queryByText("second-model")).not.toBeInTheDocument();

    await user.unhover(table);
    expect(await screen.findByText("second-model")).toBeInTheDocument();
  });

  it("shows a live status pill when connected", async () => {
    useRealtimeStore.setState((s) => ({
      connection: { ...s.connection, status: "connected" },
    }));
    renderFeed();
    expect(await screen.findByText("Live")).toBeInTheDocument();
  });

  it("shows a polling status pill when not connected", async () => {
    useRealtimeStore.setState((s) => ({
      connection: { ...s.connection, status: "offline" },
    }));
    renderFeed();
    expect(await screen.findByText("Polling")).toBeInTheDocument();
  });
});
