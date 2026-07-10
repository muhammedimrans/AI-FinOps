import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Budgets from "../features/Budgets";
import { useOrgStore } from "../stores/org";
import * as api from "../services/api";
import type { BudgetRecord, BudgetStatusSummary, BudgetSummaryResponse } from "../services/api";

// EP-24.2 — component tests for the Budgets page: list rendering, create via
// the inline editor, edit, delete-with-confirm, and the summary KPI cards.

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    listBudgets: vi.fn(),
    createBudget: vi.fn(),
    updateBudget: vi.fn(),
    deleteBudget: vi.fn(),
    getBudgetSummary: vi.fn(),
    listProjectsCrud: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const SAMPLE_BUDGET: BudgetRecord = {
  id: "budget_1",
  organization_id: "org_1",
  name: "Monthly Org Budget",
  scope_type: "organization",
  scope_project_id: null,
  scope_provider: null,
  scope_model: null,
  amount: "500.00",
  currency: "USD",
  period: "monthly",
  custom_period_start: null,
  custom_period_end: null,
  threshold_percentages: [50, 75, 90, 100],
  enabled: true,
  created_by: "user_1",
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

const SAMPLE_STATUS: BudgetStatusSummary = {
  budget: SAMPLE_BUDGET,
  current_spend: "200.00",
  remaining: "300.00",
  percent_used: 40,
  period_start: "2026-07-01",
  period_end: "2026-07-31",
  days_elapsed: 10,
  days_remaining: 21,
  projected_period_spend: "620.00",
  remaining_daily_allowance: "14.29",
  status: "healthy",
  highest_threshold_crossed: null,
};

function summaryWith(budgets: BudgetStatusSummary[]): BudgetSummaryResponse {
  return {
    budgets,
    currency: "USD",
    total_budgeted: budgets.reduce((s, b) => s + parseFloat(b.budget.amount), 0).toFixed(2),
    total_spent: budgets.reduce((s, b) => s + parseFloat(b.current_spend), 0).toFixed(2),
    total_remaining: budgets.reduce((s, b) => s + parseFloat(b.remaining), 0).toFixed(2),
    active_alert_count: 0,
    critical_alert_count: 0,
    projected_eom_spend: budgets.reduce((s, b) => s + parseFloat(b.projected_period_spend), 0).toFixed(2),
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Budgets />
    </QueryClientProvider>,
  );
}

describe("Budgets page (EP-24.2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrgStore.setState({ organizationId: "org_1", organizationName: "Acme" });
    mockedApi.listProjectsCrud.mockResolvedValue({ projects: [], total: 0 });
  });

  it("shows the empty state when there are no budgets", async () => {
    mockedApi.listBudgets.mockResolvedValue({ budgets: [], total: 0 });
    mockedApi.getBudgetSummary.mockResolvedValue(summaryWith([]));
    renderPage();
    expect(await screen.findByText(/No budgets yet/i)).toBeTruthy();
  });

  it("renders a budget card with its status and spend", async () => {
    mockedApi.listBudgets.mockResolvedValue({ budgets: [SAMPLE_BUDGET], total: 1 });
    mockedApi.getBudgetSummary.mockResolvedValue(summaryWith([SAMPLE_STATUS]));
    renderPage();

    expect(await screen.findByText("Monthly Org Budget")).toBeTruthy();
    expect(screen.getByText("Healthy")).toBeTruthy();
    expect(screen.getByText("$300.00")).toBeTruthy(); // remaining
  });

  it("shows the summary KPI cards", async () => {
    mockedApi.listBudgets.mockResolvedValue({ budgets: [SAMPLE_BUDGET], total: 1 });
    mockedApi.getBudgetSummary.mockResolvedValue(summaryWith([SAMPLE_STATUS]));
    renderPage();

    expect(await screen.findByText("Total Budgeted")).toBeTruthy();
    expect(screen.getByText("Projected EOM Spend")).toBeTruthy();
    expect(screen.getByText("Active Alerts")).toBeTruthy();
  });

  it("creates a budget via the inline editor", async () => {
    const user = userEvent.setup();
    mockedApi.listBudgets.mockResolvedValue({ budgets: [], total: 0 });
    mockedApi.getBudgetSummary.mockResolvedValue(summaryWith([]));
    mockedApi.createBudget.mockResolvedValue(SAMPLE_BUDGET);

    renderPage();
    await screen.findByText(/No budgets yet/i);

    await user.click(screen.getByRole("button", { name: /new budget/i }));
    await user.type(screen.getByPlaceholderText(/Monthly OpenAI Spend/i), "Monthly Org Budget");
    await user.type(screen.getByPlaceholderText("1000.00"), "500");
    await user.click(screen.getByRole("button", { name: "Create budget" }));

    await waitFor(() => {
      expect(mockedApi.createBudget).toHaveBeenCalledWith(
        "org_1",
        expect.objectContaining({
          name: "Monthly Org Budget",
          scope_type: "organization",
          amount: "500",
          period: "monthly",
        }),
      );
    });
  });

  it("deletes a budget after confirming", async () => {
    const user = userEvent.setup();
    mockedApi.listBudgets.mockResolvedValue({ budgets: [SAMPLE_BUDGET], total: 1 });
    mockedApi.getBudgetSummary.mockResolvedValue(summaryWith([SAMPLE_STATUS]));
    mockedApi.deleteBudget.mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Monthly Org Budget");

    await user.click(screen.getByRole("button", { name: /delete budget/i }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(mockedApi.deleteBudget).toHaveBeenCalledWith("org_1", "budget_1");
    });
  });

  it("shows the exceeded status badge for an over-budget summary", async () => {
    const exceeded: BudgetStatusSummary = {
      ...SAMPLE_STATUS,
      current_spend: "600.00",
      remaining: "-100.00",
      percent_used: 120,
      status: "exceeded",
      highest_threshold_crossed: 100,
    };
    mockedApi.listBudgets.mockResolvedValue({ budgets: [SAMPLE_BUDGET], total: 1 });
    mockedApi.getBudgetSummary.mockResolvedValue(summaryWith([exceeded]));
    renderPage();

    expect(await screen.findByText("Exceeded")).toBeTruthy();
  });
});
