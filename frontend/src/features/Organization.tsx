import { motion } from "framer-motion";
import { Building2, Users, FolderOpen, ArrowUpDown, ArrowDown, ArrowUp, Wallet, Gauge } from "lucide-react";
import { useState } from "react";
import BudgetBar from "../components/BudgetBar";
import PageHeader from "../components/PageHeader";
import OrgLogo from "../components/OrgLogo";
import EmptyState from "../components/EmptyState";
import MetricCard from "../components/MetricCard";
import { useOrganization } from "../hooks/useDashboard";
import { formatCost, formatNumber, cn } from "../utils";
import { useUIStore } from "../stores/ui";
import type { DepartmentCost } from "../types/api";

type SortKey = "department_name" | "total_cost" | "budget_utilization_pct" | "team_count" | "request_count";

export default function Organization() {
  const { currency } = useUIStore();
  const [sortKey, setSortKey] = useState<SortKey>("total_cost");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const org = useOrganization();
  const departments = org.data?.departments ?? [];
  const totalCost = parseFloat(org.data?.total_cost ?? "0");
  const totalBudget = parseFloat(org.data?.total_budget ?? "0");
  const overallUtil = totalBudget > 0 ? (totalCost / totalBudget) * 100 : 0;

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sorted = [...departments].sort((a, b) => {
    const av = String(a[sortKey as keyof DepartmentCost]);
    const bv = String(b[sortKey as keyof DepartmentCost]);
    const numA = parseFloat(av);
    const numB = parseFloat(bv);
    const result = isNaN(numA) ? av.localeCompare(bv) : numA - numB;
    return sortDir === "asc" ? result : -result;
  });

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ArrowUpDown size={10} className="opacity-40" />;
    return sortDir === "asc" ? <ArrowUp size={10} className="text-brand" /> : <ArrowDown size={10} className="text-brand" />;
  }

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader
        title="Organization"
        description="Departmental budget utilization and cost allocation."
        actions={<OrgLogo size={40} />}
      />

      {/* Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
          <MetricCard
            label="Departments"
            value={departments.length}
            type="number"
            subtitle="active"
            icon={Building2}
            gradient="teal"
            loading={org.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <MetricCard
            label="Total Spend"
            value={totalCost}
            type="currency"
            currency={currency}
            subtitle="combined"
            icon={Wallet}
            gradient="blue"
            loading={org.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <MetricCard
            label="Total Budget"
            value={totalBudget}
            type="currency"
            currency={currency}
            subtitle="allocated"
            icon={Wallet}
            gradient="emerald"
            loading={org.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <MetricCard
            label="Avg Utilization"
            value={`${overallUtil.toFixed(0)}%`}
            type="raw"
            subtitle="budget used"
            icon={Gauge}
            gradient="purple"
            loading={org.isLoading}
          />
        </motion.div>
      </div>

      {/* Overall budget bar */}
      {!org.isLoading && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass-card rounded-card-lg border border-border-subtle p-5 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent" aria-hidden="true" />
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-tx-primary">Organization Budget Overview</h3>
            <span className="text-xs text-tx-muted">
              {formatCost(totalCost, currency, true)} of {formatCost(totalBudget, currency, true)}
            </span>
          </div>
          <BudgetBar
            used={totalCost}
            total={totalBudget}
            pct={overallUtil}
            currency={currency}
            showLabels={false}
          />
        </motion.div>
      )}

      {/* Department Table */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card rounded-card-lg border border-border-subtle relative overflow-hidden"
      >
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent" aria-hidden="true" />
        <div className="px-5 py-4 border-b border-border-subtle">
          <h3 className="text-sm font-semibold text-tx-primary">Department Breakdown</h3>
          <p className="text-xs text-tx-muted mt-0.5">Cost and budget utilization by department</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full data-table">
            <thead>
              <tr>
                {(
                  [
                    { key: "department_name", label: "Department" },
                    { key: "team_count",      label: "Teams" },
                    { key: null,              label: "Projects" },
                    { key: "request_count",   label: "Requests" },
                    { key: "total_cost",      label: "Spend" },
                    { key: null,              label: "Budget" },
                    { key: "budget_utilization_pct", label: "Utilization", className: "w-48" },
                  ] as { key: SortKey | null; label: string; className?: string }[]
                ).map(({ key, label, className }) =>
                  key ? (
                    <th
                      key={label}
                      className={cn("cursor-pointer", className)}
                      tabIndex={0}
                      role="columnheader"
                      aria-sort={sortKey === key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                      onClick={() => toggleSort(key)}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleSort(key); } }}
                    >
                      <span className="flex items-center gap-1">
                        {label} <SortIcon col={key} />
                      </span>
                    </th>
                  ) : (
                    <th key={label} className={className}>{label}</th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {org.isLoading
                ? Array.from({ length: 5 }, (_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 7 }, (_, j) => (
                        <td key={j}><div className="h-4 skeleton rounded" /></td>
                      ))}
                    </tr>
                  ))
                : sorted.length === 0
                  ? (
                    <tr>
                      <td colSpan={7}>
                        <EmptyState icon={Building2} title="No departments" description="No department data available." />
                      </td>
                    </tr>
                  )
                  : sorted.map((d, i) => {
                      const isOver = d.budget_utilization_pct > 100;
                      const isNear = d.budget_utilization_pct >= 80 && !isOver;
                      return (
                        <motion.tr
                          key={d.department_id}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: i * 0.04 }}
                          className={cn(isOver && "bg-danger-dim/40", isNear && "bg-warning-dim/40")}
                        >
                          <td>
                            <div className="flex items-center gap-2">
                              <div className="w-7 h-7 rounded-lg bg-primary-subtle flex items-center justify-center flex-shrink-0">
                                <Building2 size={12} className="text-primary" />
                              </div>
                              <span className="text-tx-primary text-sm font-medium">
                                {d.department_name}
                              </span>
                            </div>
                          </td>
                          <td>
                            <span className="flex items-center gap-1 text-xs text-tx-secondary">
                              <Users size={11} className="text-tx-muted" />
                              {d.team_count}
                            </span>
                          </td>
                          <td>
                            <span className="flex items-center gap-1 text-xs text-tx-secondary">
                              <FolderOpen size={11} className="text-tx-muted" />
                              {d.project_count}
                            </span>
                          </td>
                          <td className="font-mono text-xs">{formatNumber(d.request_count, true)}</td>
                          <td className="font-semibold text-xs text-tx-primary">
                            {formatCost(d.total_cost, currency, true)}
                          </td>
                          <td className="text-xs text-tx-secondary">
                            {formatCost(d.budget, currency, true)}
                          </td>
                          <td>
                            <div className="min-w-[120px]">
                              <BudgetBar
                                used={d.total_cost}
                                total={d.budget}
                                pct={d.budget_utilization_pct}
                                currency={currency}
                                size="sm"
                              />
                            </div>
                          </td>
                        </motion.tr>
                      );
                    })}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}
