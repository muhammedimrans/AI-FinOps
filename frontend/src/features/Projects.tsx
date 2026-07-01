import { motion } from "framer-motion";
import { AlertTriangle, FolderOpen, TrendingUp, TrendingDown, FolderKanban, DollarSign, Wallet, AlertOctagon } from "lucide-react";
import BudgetBar from "../components/BudgetBar";
import EmptyState from "../components/EmptyState";
import MetricCard from "../components/MetricCard";
import { useProjects } from "../hooks/useDashboard";
import { formatCost, formatNumber, modelDisplayName } from "../lib/utils";
import { useUIStore } from "../stores/ui";
import { cn } from "../lib/utils";

function MiniTrendLine({ data, positive }: { data: string[]; positive: boolean }) {
  const nums = data.map(parseFloat);
  if (nums.length < 2) return null;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const range = max - min || 1;
  const w = 56, h = 20;
  const step = w / (nums.length - 1);

  const points = nums
    .map((v, i) => `${i * step},${h - ((v - min) / range) * h}`)
    .join(" ");

  return (
    <svg width={w} height={h}>
      <polyline
        points={points}
        fill="none"
        stroke={positive ? "rgb(var(--color-success))" : "rgb(var(--color-danger))"}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.8}
      />
    </svg>
  );
}

export default function Projects() {
  const { currency } = useUIStore();
  const projects = useProjects();

  const list = projects.data?.projects ?? [];
  const overBudget = list.filter((p) => p.budget_utilization_pct > 100);
  const nearBudget = list.filter((p) => p.budget_utilization_pct >= 80 && p.budget_utilization_pct <= 100);

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      {/* Alert banner */}
      {!projects.isLoading && (overBudget.length > 0 || nearBudget.length > 0) && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className={cn(
            "rounded-card p-4 flex items-start gap-3 border",
            overBudget.length > 0
              ? "bg-danger-dim border-danger/30"
              : "bg-warning-dim border-warning/30",
          )}
        >
          <AlertTriangle
            size={16}
            className={overBudget.length > 0 ? "text-danger mt-0.5" : "text-warning mt-0.5"}
          />
          <div>
            <p className={cn("text-sm font-semibold", overBudget.length > 0 ? "text-danger" : "text-warning")}>
              {overBudget.length > 0
                ? `${overBudget.length} project${overBudget.length > 1 ? "s" : ""} over budget`
                : `${nearBudget.length} project${nearBudget.length > 1 ? "s" : ""} approaching budget limit`}
            </p>
            <p className="text-xs text-tx-secondary mt-0.5">
              {overBudget.length > 0
                ? overBudget.map((p) => p.project_name).join(", ") + " exceeded allocated budget."
                : nearBudget.map((p) => p.project_name).join(", ") + " are over 80% of budget."}
            </p>
          </div>
        </motion.div>
      )}

      {/* Summary stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
          <MetricCard
            label="Total Projects"
            value={list.length}
            type="number"
            subtitle="active"
            icon={FolderKanban}
            gradient="teal"
            loading={projects.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <MetricCard
            label="Total Spend"
            value={list.reduce((s, p) => s + parseFloat(p.total_cost), 0)}
            type="currency"
            currency={currency}
            subtitle="combined"
            icon={DollarSign}
            gradient="blue"
            loading={projects.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <MetricCard
            label="Total Budget"
            value={list.reduce((s, p) => s + parseFloat(p.budget), 0)}
            type="currency"
            currency={currency}
            subtitle="allocated"
            icon={Wallet}
            gradient="emerald"
            loading={projects.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <MetricCard
            label="Over Budget"
            value={overBudget.length}
            type="number"
            subtitle={overBudget.length > 0 ? "needs attention" : "all in range"}
            icon={AlertOctagon}
            gradient={overBudget.length > 0 ? "amber" : "teal"}
            loading={projects.isLoading}
          />
        </motion.div>
      </div>

      {/* Project Cards Grid */}
      {projects.isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="h-64 skeleton rounded-card" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="No projects found"
          description="No projects with AI spend in the selected period."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {list.map((p, i) => {
            const isOver = p.budget_utilization_pct > 100;
            const isNear = p.budget_utilization_pct >= 80 && !isOver;
            const positive = p.cost_trend < 0;
            return (
              <motion.div
                key={p.project_id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
                whileHover={{ y: -3, transition: { duration: 0.2, ease: "easeOut" } }}
                className={cn(
                  "glass-card rounded-card-lg border p-5 cursor-pointer transition-shadow duration-base hover:shadow-elevated",
                  isOver ? "border-danger/30" : isNear ? "border-warning/30" : "border-border-subtle",
                )}
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-sm font-semibold text-tx-primary">{p.project_name}</h3>
                    <p className="text-xs text-tx-muted mt-0.5">{p.team} Team</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {p.cost_trend !== 0 && (
                      <span className={cn("flex items-center gap-0.5 text-xs font-medium", positive ? "text-success" : "text-danger")}>
                        {positive ? <TrendingDown size={11} /> : <TrendingUp size={11} />}
                        {Math.abs(p.cost_trend).toFixed(1)}%
                      </span>
                    )}
                    <MiniTrendLine data={p.trend_data} positive={positive} />
                  </div>
                </div>

                {/* Budget bar */}
                <div className="mb-4">
                  <BudgetBar
                    used={p.total_cost}
                    total={p.budget}
                    pct={p.budget_utilization_pct}
                    currency={currency}
                  />
                </div>

                {/* Stats */}
                <div className="flex items-center justify-between text-xs text-tx-muted mb-3">
                  <span>{formatNumber(p.request_count, true)} requests</span>
                  <span className="font-semibold text-tx-primary">{formatCost(p.total_cost, currency, true)}</span>
                </div>

                {/* Top models */}
                <div className="flex flex-wrap gap-1">
                  {p.top_models.slice(0, 2).map((m) => (
                    <span key={m} className="text-[10px] font-mono bg-app-muted text-tx-muted px-1.5 py-0.5 rounded">
                      {modelDisplayName(m)}
                    </span>
                  ))}
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
