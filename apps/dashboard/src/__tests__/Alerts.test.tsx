import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Alerts from "../features/Alerts";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type { AlertRecord } from "../services/api";

// EP-24.2 — component tests for the Alert Center page: list rendering,
// severity/status filters, and the acknowledge/resolve/dismiss/reopen
// lifecycle actions (all reusing the existing EP-19.3 alert endpoints).

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listAlerts: vi.fn(),
    acknowledgeAlert: vi.fn(),
    resolveAlert: vi.fn(),
    dismissAlert: vi.fn(),
    reopenAlert: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function makeAlert(overrides: Partial<AlertRecord> = {}): AlertRecord {
  return {
    id: "alert_1",
    alert_type: "budget_exceeded",
    severity: "critical",
    status: "open",
    title: "Monthly Org Budget: budget exceeded (100%)",
    message: "This organization has spent 620.00 USD of its 500.00 USD monthly budget.",
    source: "budget_evaluation",
    occurrence_count: 1,
    metadata: { budget_name: "Monthly Org Budget", scope_type: "organization" },
    first_occurred_at: "2026-07-10T00:00:00Z",
    last_occurred_at: "2026-07-10T00:00:00Z",
    acknowledged_by: null,
    acknowledged_at: null,
    acknowledgement_reason: null,
    resolved_at: null,
    dismissed_at: null,
    created_at: "2026-07-10T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Alerts />
    </QueryClientProvider>,
  );
}

describe("Alerts page (EP-24.2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
  });

  it("shows the empty state when there are no alerts", async () => {
    mockedApi.listAlerts.mockResolvedValue({ alerts: [], total: 0 });
    renderPage();
    expect(await screen.findByText(/No alerts/i)).toBeTruthy();
  });

  it("renders an alert with its severity and status badges", async () => {
    mockedApi.listAlerts.mockResolvedValue({ alerts: [makeAlert()], total: 1 });
    renderPage();

    expect(await screen.findByText(/budget exceeded \(100%\)/i)).toBeTruthy();
    expect(screen.getAllByText("critical").length).toBeGreaterThan(0);
    expect(screen.getAllByText("open").length).toBeGreaterThan(0);
  });

  it("shows the open/critical summary counts", async () => {
    mockedApi.listAlerts.mockResolvedValue({ alerts: [makeAlert()], total: 1 });
    renderPage();

    await screen.findByText(/budget exceeded/i);
    expect(screen.getByText("Open")).toBeTruthy();
    expect(screen.getByText("Critical")).toBeTruthy();
  });

  it("acknowledges an open alert", async () => {
    const user = userEvent.setup();
    mockedApi.listAlerts.mockResolvedValue({ alerts: [makeAlert()], total: 1 });
    mockedApi.acknowledgeAlert.mockResolvedValue(makeAlert({ status: "acknowledged" }));

    renderPage();
    await screen.findByText(/budget exceeded/i);
    await user.click(screen.getByRole("button", { name: /acknowledge/i }));

    await waitFor(() => {
      expect(mockedApi.acknowledgeAlert).toHaveBeenCalledWith("org_1", "alert_1", undefined);
    });
  });

  it("resolves an open alert", async () => {
    const user = userEvent.setup();
    mockedApi.listAlerts.mockResolvedValue({ alerts: [makeAlert()], total: 1 });
    mockedApi.resolveAlert.mockResolvedValue(makeAlert({ status: "resolved" }));

    renderPage();
    await screen.findByText(/budget exceeded/i);
    await user.click(screen.getByRole("button", { name: "Resolve" }));

    await waitFor(() => {
      expect(mockedApi.resolveAlert).toHaveBeenCalledWith("org_1", "alert_1");
    });
  });

  it("dismisses (archives) an open alert", async () => {
    const user = userEvent.setup();
    mockedApi.listAlerts.mockResolvedValue({ alerts: [makeAlert()], total: 1 });
    mockedApi.dismissAlert.mockResolvedValue(makeAlert({ status: "dismissed" }));

    renderPage();
    await screen.findByText(/budget exceeded/i);
    await user.click(screen.getByRole("button", { name: /dismiss alert/i }));

    await waitFor(() => {
      expect(mockedApi.dismissAlert).toHaveBeenCalledWith("org_1", "alert_1");
    });
  });

  it("reopens a resolved alert", async () => {
    const user = userEvent.setup();
    mockedApi.listAlerts.mockResolvedValue({ alerts: [makeAlert({ status: "resolved" })], total: 1 });
    mockedApi.reopenAlert.mockResolvedValue(makeAlert({ status: "open" }));

    renderPage();
    await screen.findByText(/budget exceeded/i);
    await user.click(screen.getByRole("button", { name: /reopen/i }));

    await waitFor(() => {
      expect(mockedApi.reopenAlert).toHaveBeenCalledWith("org_1", "alert_1");
    });
  });

  it("filters by severity", async () => {
    const user = userEvent.setup();
    mockedApi.listAlerts.mockResolvedValue({ alerts: [makeAlert()], total: 1 });
    renderPage();
    await screen.findByText(/budget exceeded/i);

    await user.selectOptions(screen.getByLabelText("Filter by severity"), "high");

    await waitFor(() => {
      const lastCall = mockedApi.listAlerts.mock.calls.at(-1)?.[0];
      expect(lastCall?.severity).toBe("high");
    });
  });
});
