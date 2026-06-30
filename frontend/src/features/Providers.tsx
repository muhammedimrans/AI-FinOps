import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { motion } from "framer-motion";
import { TrendingUp, Activity, Boxes, Zap } from "lucide-react";
import ChartCard from "../components/ChartCard";
import ProviderBadge, { PROVIDER_COLORS } from "../components/ProviderBadge";
import { useProviders, useModels } from "../hooks/useDashboard";
import { formatCost, formatNumber, formatTokens, providerDisplayName } from "../lib/utils";
import { useUIStore } from "../stores/ui";

const TOOLTIP_STYLE = {
  backgroundColor: "#12121A",
  border: "1px solid #1E293B",
  borderRadius: 8,
  color: "#F8FAFC",
  fontSize: 12,
};

type Metric = "cost" | "requests" | "tokens";

export default function Providers() {
  const { currency } = useUIStore();
  const [metric, setMetric] = useState<Metric>("cost");

  const providers = useProviders();
  const models = useModels();

  const providerList = providers.data?.providers ?? [];
  const modelList = models.data?.models ?? [];

  const chartData = providerList.map((p) => ({
    name: providerDisplayName(p.provider).slice(0, 10),
    cost: parseFloat(p.total_cost),
    requests: p.request_count,
    tokens: (p.input_tokens + p.output_tokens) / 1_000_000,
    provider: p.provider,
  }));

  const metricLabel =
    metric === "cost" ? `Cost (${currency})` : metric === "requests" ? "Requests" : "Tokens (M)";

  const metricFormatter = (v: number) =>
    metric === "cost"
      ? formatCost(v, currency, true)
      : metric === "tokens"
        ? `${v.toFixed(1)}M`
        : formatNumber(v, true);

  return (
    <div className="p-6 space-y-6">
      {/* Provider Cards */}
      {providers.isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="glass-card border border-border-subtle p-5 h-44 skeleton" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {providerList.map((p, i) => {
            const modelCount = modelList.filter((m) => m.provider === p.provider).length;
            const cost = parseFloat(p.total_cost);
            return (
              <motion.div
                key={p.provider}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
                whileHover={{ y: -2 }}
                className="glass-card border border-border-subtle p-5 cursor-pointer transition-shadow hover:shadow-card-hover"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center mb-3"
                      style={{ background: `${PROVIDER_COLORS[p.provider]}22` }}
                    >
                      <span
                        className="text-sm font-bold"
                        style={{ color: PROVIDER_COLORS[p.provider] }}
                      >
                        {providerDisplayName(p.provider).slice(0, 2).toUpperCase()}
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-tx-primary">
                      {providerDisplayName(p.provider)}
                    </h3>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="badge bg-success-dim text-success text-[10px]">● Active</span>
                    <span className="text-xs text-tx-muted">{p.cost_share_pct}% share</span>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-tx-muted flex items-center gap-1">
                      <TrendingUp size={11} /> Total Spend
                    </span>
                    <span className="text-sm font-bold text-tx-primary">
                      {formatCost(cost, currency, true)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-tx-muted flex items-center gap-1">
                      <Activity size={11} /> Requests
                    </span>
                    <span className="text-xs text-tx-secondary">
                      {formatNumber(p.request_count, true)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-tx-muted flex items-center gap-1">
                      <Boxes size={11} /> Models
                    </span>
                    <span className="text-xs text-tx-secondary">{modelCount}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-tx-muted flex items-center gap-1">
                      <Zap size={11} /> Tokens
                    </span>
                    <span className="text-xs text-tx-secondary">
                      {formatTokens(p.input_tokens + p.output_tokens)}
                    </span>
                  </div>
                </div>

                {/* Cost share bar */}
                <div className="mt-4 pt-4 border-t border-border-subtle">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-tx-muted">Cost share</span>
                    <span className="text-[10px] font-semibold" style={{ color: PROVIDER_COLORS[p.provider] }}>
                      {p.cost_share_pct}%
                    </span>
                  </div>
                  <div className="h-1.5 bg-app-muted rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${p.cost_share_pct}%` }}
                      transition={{ duration: 0.6, delay: i * 0.08 }}
                      className="h-full rounded-full"
                      style={{ background: PROVIDER_COLORS[p.provider] }}
                    />
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Comparison Chart */}
      <ChartCard
        title="Provider Comparison"
        subtitle="Side-by-side provider metrics"
        loading={providers.isLoading}
        minHeight={300}
        actions={
          <div className="flex gap-1 bg-app-bg rounded-lg p-0.5">
            {(["cost", "requests", "tokens"] as Metric[]).map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all capitalize
                  ${metric === m ? "bg-app-card text-tx-primary shadow-card" : "text-tx-muted hover:text-tx-secondary"}`}
              >
                {m}
              </button>
            ))}
          </div>
        }
      >
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
            <XAxis dataKey="name" tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fill: "#475569", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={metricFormatter}
              width={60}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              formatter={(v: number) => metricFormatter(v)}
              labelStyle={{ color: "#94A3B8" }}
            />
            <Bar
              dataKey={metric}
              name={metricLabel}
              radius={[4, 4, 0, 0]}
              fill="#4F46E5"
            />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Models by provider table */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass-card border border-border-subtle">
        <div className="px-5 py-4 border-b border-border-subtle">
          <h3 className="text-sm font-semibold text-tx-primary">All Models</h3>
          <p className="text-xs text-tx-muted mt-0.5">All active models across providers</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full data-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Model</th>
                <th className="text-right">Requests</th>
                <th className="text-right">Input Tokens</th>
                <th className="text-right">Output Tokens</th>
                <th className="text-right">$/1K Tokens</th>
                <th className="text-right">Total Cost</th>
              </tr>
            </thead>
            <tbody>
              {models.isLoading
                ? Array.from({ length: 8 }, (_, i) => (
                    <tr key={i}>
                      {[...Array(7)].map((_, j) => (
                        <td key={j}><div className="h-4 skeleton rounded" /></td>
                      ))}
                    </tr>
                  ))
                : [...modelList]
                    .sort((a, b) => parseFloat(b.total_cost) - parseFloat(a.total_cost))
                    .map((m) => (
                      <tr key={m.model_id}>
                        <td><ProviderBadge provider={m.provider} size="sm" /></td>
                        <td className="font-mono text-xs text-tx-primary">{m.model_id}</td>
                        <td className="text-right font-mono text-xs">{formatNumber(m.request_count)}</td>
                        <td className="text-right font-mono text-xs">{formatTokens(m.input_tokens)}</td>
                        <td className="text-right font-mono text-xs">{formatTokens(m.output_tokens)}</td>
                        <td className="text-right font-mono text-xs">{formatCost(m.cost_per_1k_tokens, currency)}</td>
                        <td className="text-right font-semibold text-xs text-tx-primary">
                          {formatCost(m.total_cost, currency, true)}
                        </td>
                      </tr>
                    ))}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}
