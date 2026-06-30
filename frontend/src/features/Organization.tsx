import { motion } from "framer-motion";
import { Building2, Users, FolderOpen, ArrowUpDown, ArrowDown, ArrowUp } from "lucide-react";
import { useState } from "react";
import BudgetBar from "../components/BudgetBar";
import EmptyState from "../components/EmptyState";
import { useOrganization } from "../hooks/useDashboard";
import { formatCost, formatNumber } from "../lib/utils";
import { useUIStore } from "../stores/ui";
import { cn } from "../lib/utils";
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
    if (sortKey !== col) return <ArrowUpDown size={11} className="opacity-30" />;
    return sortDir === "asc" ? <ArrowUp size={11} className="text-primary" /> : <ArrowDown size={11} className="text-primary" />;
  }

  return (
    <div className="p-6 space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Departments",   value: departments.length,  icon: Building2, sub: "active"    },
          { label: "Total Spend",   value: formatCost(totalCost, currency, true), icon: null, sub: "combined" },
          { label: "Total Budget",  value: formatCost(totalBudget, currency, true), icon: null, sub: "allocated" },
          { label: "Avg Utilization", value: `${overallUtil.toFixed(0)}%`, icon: null, sub: "budget used" },
        ].map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="glass-card border border-border-subtle p-5"
          >
            <p className="text-xs text-tx-muted mb-1">{s.label}</p>
            <p className="text-xl font-bold text-tx-primary">
              {org.isLoading ? "—" : s.value}
            </p>
            <p className="text-xs text-tx-muted mt-1">{s.sub}</p>
          </motion.div>
        ))}
      </div>

      {/* Overall budget bar */}
      {!org.isLoading && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass-card border border-border-subtle p-5">
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
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass-card border border-border-subtle">
        <div className="px-5 py-4 border-b border-border-subtle">
          <h3 className="text-sm font-semibold text-tx-primary">Department Breakdown</h3>
          <p className="text-xs text-tx-muted mt-0.5">Cost and budget utilization by department</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full data-table">
            <thead>
              <tr>
                <th
                  className="cursor-pointer"
                  onClick={() => toggleSort("department_name")}
                >
                  <span className="flex items-center gap-1">
                    Department <SortIcon col="department_name" />
                  </span>
                </th>
                <th
                  className="cursor-pointer"
                  onClick={() => toggleSort("team_count")}
                >
                  <span className="flex items-center gap-1">
                    Teams <SortIcon col="team_count" />
                  </span>
                </th>
                <th>Projects</th>
                <th
                  className="cursor-pointer"
                  onClick={() => toggleSort("request_count")}
                >
                  <span className="flex items-center gap-1">
                    Requests <SortIcon col="request_count" />
                  </span>
                </th>
                <th
                  className="cursor-pointer"
                  onClick={() => toggleSort("total_cost")}
                >
                  <span className="flex items-center gap-1">
                    Spend <SortIcon col="total_cost" />
                  </span>
                </th>
                <th>Budget</th>
                <th
                  className="cursor-pointer w-48"
                  onClick={() => toggleSort("budget_utilization_pct")}
                >
                  <span className="flex items-center gap-1">
                    Utilization <SortIcon col="budget_utilization_pct" />
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {org.isLoading
                ? Array.from({ length: 5 }, (_, i) => (
                    <tr key={i}>
                      {[...Array(7)].map((_, j) => (
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
