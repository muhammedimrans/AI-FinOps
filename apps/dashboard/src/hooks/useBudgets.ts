import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOrgStore } from "../stores/org";
import { useUIStore } from "../stores/ui";
import * as api from "../services/api";
import type { CreateBudgetRequest, UpdateBudgetRequest } from "../services/api";

const BUDGETS_KEY = "budgets";
const BUDGET_SUMMARY_KEY = "budget-summary";

/** Every configured budget, each with its own server-derived spend/forecast/
 * status (BudgetEvaluationService, EP-24.2) — backs the Budgets page. */
export function useBudgets() {
  const { organizationId } = useOrgStore();
  return useQuery({
    queryKey: [BUDGETS_KEY, organizationId],
    queryFn: () => api.listBudgets(organizationId!),
    enabled: !!organizationId,
  });
}

/** Org-wide budget summary (per-budget status + Budget Remaining / Active
 * Alerts / Critical Alerts / Projected End-of-Month Spend) — backs the
 * Overview KPI cards and the Budgets page's top summary row. Polled every
 * 60s so a background sync's budget evaluation (scheduler or manual sync)
 * shows up without a manual refresh, matching the existing dashboard hooks'
 * polling-fallback convention. */
export function useBudgetSummary() {
  const { organizationId } = useOrgStore();
  const { currency } = useUIStore();
  return useQuery({
    queryKey: [BUDGET_SUMMARY_KEY, organizationId, currency],
    queryFn: () => api.getBudgetSummary(organizationId!, currency),
    enabled: !!organizationId,
    refetchInterval: 60_000,
  });
}

export function useBudgetMutations() {
  const { organizationId } = useOrgStore();
  const queryClient = useQueryClient();

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: [BUDGETS_KEY, organizationId] });
    void queryClient.invalidateQueries({ queryKey: [BUDGET_SUMMARY_KEY, organizationId] });
  };

  const create = useMutation({
    mutationFn: (body: CreateBudgetRequest) => api.createBudget(organizationId!, body),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: (vars: { budgetId: string; body: UpdateBudgetRequest }) =>
      api.updateBudget(organizationId!, vars.budgetId, vars.body),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (budgetId: string) => api.deleteBudget(organizationId!, budgetId),
    onSuccess: invalidate,
  });

  return { create, update, remove };
}
