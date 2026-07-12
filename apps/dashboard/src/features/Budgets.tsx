import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import {
  Wallet,
  Plus,
  Pencil,
  Trash2,
  TrendingUp,
  AlertTriangle,
  DollarSign,
  Gauge,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import MetricCard from "../components/MetricCard";
import ConfirmDialog from "../components/ConfirmDialog";
import BudgetBar from "../components/BudgetBar";
import { useBudgets, useBudgetSummary, useBudgetMutations } from "../hooks/useBudgets";
import { listProjectsCrud, ApiError } from "../services/api";
import type {
  BudgetRecord,
  BudgetScopeType,
  BudgetPeriodType,
  BudgetStatusSummary,
  CreateBudgetRequest,
} from "../services/api";
import { CONNECTABLE_PROVIDERS } from "../lib/providerCatalog";
import { formatCost, cn } from "../utils";
import { useOrgStore } from "../stores/org";
import { useUIStore } from "../stores/ui";
import { toast } from "../stores/toast";

const SCOPE_LABELS: Record<BudgetScopeType, string> = {
  organization: "Organization",
  project: "Project",
  provider: "Provider",
  model: "Model",
};

const PERIOD_LABELS: Record<BudgetPeriodType, string> = {
  daily: "Daily",
  weekly: "Weekly",
  monthly: "Monthly",
  yearly: "Yearly",
  custom: "Custom",
};

const STATUS_LABELS: Record<BudgetStatusSummary["status"], string> = {
  healthy: "Healthy",
  warning: "Warning",
  critical: "Critical",
  exceeded: "Exceeded",
};

const STATUS_BADGE: Record<BudgetStatusSummary["status"], string> = {
  healthy: "bg-success-dim text-success",
  warning: "bg-warning-dim text-warning",
  critical: "bg-warning-dim text-warning border border-warning/40",
  exceeded: "bg-danger-dim text-danger",
};

function StatusBadge({ status }: { status: BudgetStatusSummary["status"] }) {
  return (
    <span className={cn("badge text-[10px] font-semibold", STATUS_BADGE[status])}>
      {STATUS_LABELS[status]}
    </span>
  );
}

function scopeDescription(budget: BudgetRecord): string {
  if (budget.scope_type === "provider" && budget.scope_provider) {
    return CONNECTABLE_PROVIDERS.find((p) => p.value === budget.scope_provider)?.label
      ?? budget.scope_provider;
  }
  if (budget.scope_type === "model" && budget.scope_model) return budget.scope_model;
  return SCOPE_LABELS[budget.scope_type];
}

const DEFAULT_THRESHOLDS = "50, 75, 90, 100";

function BudgetEditorForm({
  organizationId,
  existing,
  onDone,
  onCancel,
}: {
  organizationId: string;
  existing?: BudgetRecord;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { create, update } = useBudgetMutations();
  const isEditing = !!existing;

  const [name, setName] = useState(existing?.name ?? "");
  const [scopeType, setScopeType] = useState<BudgetScopeType>(existing?.scope_type ?? "organization");
  const [scopeProjectId, setScopeProjectId] = useState(existing?.scope_project_id ?? "");
  const [scopeProvider, setScopeProvider] = useState(existing?.scope_provider ?? "openai");
  const [scopeModel, setScopeModel] = useState(existing?.scope_model ?? "");
  const [amount, setAmount] = useState(existing?.amount ?? "");
  const [currency, setCurrency] = useState(existing?.currency ?? "USD");
  const [period, setPeriod] = useState<BudgetPeriodType>(existing?.period ?? "monthly");
  const [thresholds, setThresholds] = useState(
    existing?.threshold_percentages.join(", ") ?? DEFAULT_THRESHOLDS,
  );

  const projects = useQuery({
    queryKey: ["projects-crud", organizationId],
    queryFn: () => listProjectsCrud(organizationId),
    enabled: scopeType === "project",
  });

  const pending = create.isPending || update.isPending;

  function parsedThresholds(): number[] {
    return thresholds
      .split(",")
      .map((t) => parseFloat(t.trim()))
      .filter((t) => Number.isFinite(t) && t > 0);
  }

  function isValid(): boolean {
    if (name.trim().length === 0) return false;
    if (!amount || Number.isNaN(parseFloat(amount)) || parseFloat(amount) <= 0) return false;
    if (parsedThresholds().length === 0) return false;
    if (scopeType === "project" && !scopeProjectId) return false;
    if (scopeType === "provider" && !scopeProvider) return false;
    if (scopeType === "model" && !scopeModel.trim()) return false;
    return true;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid()) return;

    if (isEditing) {
      update.mutate(
        {
          budgetId: existing.id,
          body: {
            name: name.trim(),
            amount,
            currency,
            period,
            threshold_percentages: parsedThresholds(),
          },
        },
        {
          onSuccess: () => {
            toast.success("Budget updated");
            onDone();
          },
          onError: (err: unknown) =>
            toast.error("Couldn't update budget", err instanceof ApiError ? err.message : "Please try again."),
        },
      );
      return;
    }

    const body: CreateBudgetRequest = {
      name: name.trim(),
      scope_type: scopeType,
      amount,
      currency,
      period,
      threshold_percentages: parsedThresholds(),
      ...(scopeType === "project" ? { scope_project_id: scopeProjectId } : {}),
      ...(scopeType === "provider" ? { scope_provider: scopeProvider } : {}),
      ...(scopeType === "model" ? { scope_model: scopeModel.trim() } : {}),
    };

    create.mutate(body, {
      onSuccess: () => {
        toast.success("Budget created", `"${name.trim()}" is now being tracked.`);
        onDone();
      },
      onError: (err: unknown) =>
        toast.error("Couldn't create budget", err instanceof ApiError ? err.message : "Please try again."),
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-xl border border-border-subtle bg-app-muted p-4"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-xs text-tx-muted">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Monthly OpenAI Spend"
            disabled={pending}
            autoFocus
            className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
          />
        </label>

        <label className="flex flex-col gap-1 text-xs text-tx-muted">
          Scope
          <select
            value={scopeType}
            onChange={(e) => setScopeType(e.target.value as BudgetScopeType)}
            disabled={pending || isEditing}
            className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
          >
            {(Object.keys(SCOPE_LABELS) as BudgetScopeType[]).map((s) => (
              <option key={s} value={s}>
                {SCOPE_LABELS[s]}
              </option>
            ))}
          </select>
        </label>

        {scopeType === "project" && !isEditing && (
          <label className="flex flex-col gap-1 text-xs text-tx-muted sm:col-span-2">
            Project
            <select
              value={scopeProjectId}
              onChange={(e) => setScopeProjectId(e.target.value)}
              disabled={pending}
              className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
            >
              <option value="">Select a project…</option>
              {(projects.data?.projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        )}

        {scopeType === "provider" && !isEditing && (
          <label className="flex flex-col gap-1 text-xs text-tx-muted sm:col-span-2">
            Provider
            <select
              value={scopeProvider}
              onChange={(e) => setScopeProvider(e.target.value)}
              disabled={pending}
              className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
            >
              {CONNECTABLE_PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
        )}

        {scopeType === "model" && !isEditing && (
          <label className="flex flex-col gap-1 text-xs text-tx-muted sm:col-span-2">
            Model
            <input
              value={scopeModel}
              onChange={(e) => setScopeModel(e.target.value)}
              placeholder="e.g. gpt-4"
              disabled={pending}
              className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
            />
          </label>
        )}

        <label className="flex flex-col gap-1 text-xs text-tx-muted">
          Amount
          <div className="flex gap-2">
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="1000.00"
              inputMode="decimal"
              disabled={pending}
              className="flex-1 rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
            />
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              disabled={pending}
              className="rounded-lg border border-border-subtle bg-app-bg px-2 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
            >
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
            </select>
          </div>
        </label>

        <label className="flex flex-col gap-1 text-xs text-tx-muted">
          Period
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as BudgetPeriodType)}
            disabled={pending}
            className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
          >
            {(Object.keys(PERIOD_LABELS) as BudgetPeriodType[])
              .filter((p) => p !== "custom")
              .map((p) => (
                <option key={p} value={p}>
                  {PERIOD_LABELS[p]}
                </option>
              ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs text-tx-muted sm:col-span-2">
          Alert thresholds (%)
          <input
            value={thresholds}
            onChange={(e) => setThresholds(e.target.value)}
            placeholder="50, 75, 90, 100"
            disabled={pending}
            className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
          />
          <span className="text-[11px] text-tx-muted">
            Comma-separated. Each fires its own alert independently — 100%+ counts as budget
            exceeded.
          </span>
        </label>
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <button type="button" onClick={onCancel} disabled={pending} className="btn-ghost h-9 px-3 text-xs">
          Cancel
        </button>
        <button
          type="submit"
          disabled={pending || !isValid()}
          className="btn-primary h-9 px-4 text-xs disabled:opacity-60"
        >
          {pending ? "Saving…" : isEditing ? "Save changes" : "Create budget"}
        </button>
      </div>
    </form>
  );
}

function BudgetCard({
  organizationId,
  summary,
}: {
  organizationId: string;
  summary: BudgetStatusSummary;
}) {
  const { currency } = useUIStore();
  const { remove } = useBudgetMutations();
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const budget = summary.budget;

  if (editing) {
    return (
      <BudgetEditorForm
        organizationId={organizationId}
        existing={budget}
        onDone={() => setEditing(false)}
        onCancel={() => setEditing(false)}
      />
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "glass-card rounded-card-lg border p-5",
        summary.status === "exceeded"
          ? "border-danger/30"
          : summary.status === "critical" || summary.status === "warning"
            ? "border-warning/30"
            : "border-border-subtle",
      )}
    >
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-tx-primary truncate">{budget.name}</h3>
          <p className="text-xs text-tx-muted mt-0.5">
            {scopeDescription(budget)} · {PERIOD_LABELS[budget.period]}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <StatusBadge status={summary.status} />
          <button onClick={() => setEditing(true)} className="icon-btn" aria-label="Edit budget">
            <Pencil size={13} />
          </button>
          <button
            onClick={() => setConfirmingDelete(true)}
            className="icon-btn icon-btn-danger"
            aria-label="Delete budget"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      <div className="mb-4">
        <BudgetBar
          used={summary.current_spend}
          total={budget.amount}
          pct={summary.percent_used}
          currency={currency}
          status={summary.status}
        />
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-tx-muted">Remaining</p>
          <p className="font-semibold text-tx-primary tabular-nums">
            {formatCost(summary.remaining, currency, true)}
          </p>
        </div>
        <div>
          <p className="text-tx-muted">Forecast (end of period)</p>
          <p
            className={cn(
              "font-semibold tabular-nums",
              parseFloat(summary.projected_period_spend) > parseFloat(budget.amount)
                ? "text-danger"
                : "text-tx-primary",
            )}
          >
            {formatCost(summary.projected_period_spend, currency, true)}
          </p>
        </div>
      </div>

      <p className="text-[11px] text-tx-muted mt-3">
        {summary.days_remaining} day{summary.days_remaining === 1 ? "" : "s"} left ·{" "}
        {formatCost(summary.remaining_daily_allowance, currency, true)}/day allowance
      </p>

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this budget?"
        description={`"${budget.name}" will stop being tracked and its alerts will no longer fire. This can't be undone.`}
        confirmLabel="Delete"
        loading={remove.isPending}
        onConfirm={() =>
          remove.mutate(budget.id, { onSuccess: () => setConfirmingDelete(false) })
        }
        onCancel={() => setConfirmingDelete(false)}
      />
    </motion.div>
  );
}

export default function Budgets() {
  const organizationId = useOrgStore((s) => s.organizationId);
  const { currency } = useUIStore();
  const [creating, setCreating] = useState(false);

  const budgets = useBudgets();
  const summary = useBudgetSummary();

  const summaries = summary.data?.budgets ?? [];
  const loading = budgets.isLoading || summary.isLoading;

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader
        title="Budgets"
        description="Set spending ceilings by organization, project, provider, or model — and get alerted before you exceed them."
        actions={
          !creating && (
            <button
              onClick={() => setCreating(true)}
              className="btn-primary h-9 px-4 text-xs inline-flex items-center gap-1.5"
            >
              <Plus size={14} /> New budget
            </button>
          )
        }
      />

      {creating && organizationId && (
        <Section title="New budget" icon={Wallet}>
          <BudgetEditorForm
            organizationId={organizationId}
            onDone={() => setCreating(false)}
            onCancel={() => setCreating(false)}
          />
        </Section>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Total Budgeted"
          value={summary.data?.total_budgeted ?? "0"}
          type="currency"
          currency={currency}
          subtitle={`${summaries.length} budget${summaries.length === 1 ? "" : "s"}`}
          icon={Wallet}
          gradient="teal"
          loading={summary.isLoading}
        />
        <MetricCard
          label="Total Spent"
          value={summary.data?.total_spent ?? "0"}
          type="currency"
          currency={currency}
          subtitle="across all budgets"
          icon={DollarSign}
          gradient="blue"
          loading={summary.isLoading}
        />
        <MetricCard
          label="Projected EOM Spend"
          value={summary.data?.projected_eom_spend ?? "0"}
          type="currency"
          currency={currency}
          subtitle="deterministic forecast"
          icon={TrendingUp}
          gradient="amber"
          loading={summary.isLoading}
        />
        <MetricCard
          label="Active Alerts"
          value={summary.data?.active_alert_count ?? 0}
          type="number"
          subtitle={`${summary.data?.critical_alert_count ?? 0} critical`}
          icon={AlertTriangle}
          gradient={(summary.data?.critical_alert_count ?? 0) > 0 ? "amber" : "teal"}
          loading={summary.isLoading}
        />
      </div>

      <Section
        title="Your budgets"
        description="Current spend, remaining allowance, and forecast for each configured budget."
        icon={Gauge}
      >
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Array.from({ length: 2 }, (_, i) => <div key={i} className="h-48 skeleton rounded-card" />)}
          </div>
        ) : summaries.length === 0 ? (
          <EmptyState
            icon={Wallet}
            title="No budgets yet"
            description="Create a budget to start tracking spend and get alerted before you exceed it."
            action={
              !creating && organizationId ? (
                <button onClick={() => setCreating(true)} className="btn-primary h-9 px-4 text-sm">
                  Create budget
                </button>
              ) : undefined
            }
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {summaries.map((s) => (
              <BudgetCard key={s.budget.id} organizationId={organizationId!} summary={s} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
