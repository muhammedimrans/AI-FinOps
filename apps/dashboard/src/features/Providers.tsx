import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
} from "recharts";
import { motion } from "framer-motion";
import { TrendingUp, Activity, Boxes, Zap, Plug } from "lucide-react";
import ChartCard from "../components/ChartCard";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import ProviderBadge from "../components/ProviderBadge";
import { useProviders, useModels } from "../hooks/useDashboard";
import { formatCost, formatNumber, formatTokens, providerDisplayName } from "../utils";
import { useUIStore } from "../stores/ui";
import { useChartChrome } from "../lib/chartPalette";
import { PROVIDER_CATALOG, PROVIDER_COLORS } from "../lib/providerCatalog";

type Metric = "cost" | "requests" | "tokens";

export default function Providers() {
  const { currency } = useUIStore();
  const chrome = useChartChrome();
  const tooltipStyle = {
    backgroundColor: chrome.tooltipBg,
    border: `1px solid ${chrome.tooltipBorder}`,
    borderRadius: 12,
    color: chrome.text,
    fontSize: 12,
    boxShadow: "0 12px 32px rgb(var(--shadow-rgb) / var(--shadow-a-5))",
    backdropFilter: "blur(12px)",
  };
  const [metric, setMetric] = useState<Metric>("cost");
  const [hoveredBar, setHoveredBar] = useState<number | null>(null);

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
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader title="Providers" description="Compare cost, requests, and usage across every connected AI provider." />

      {/* Provider Cards */}
      {providers.isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="glass-card rounded-card-lg border border-border-subtle p-5 h-44 skeleton" />
          ))}
        </div>
      ) : providerList.length === 0 ? (
        <EmptyState
          icon={Plug}
          title="No providers found"
          description="No AI provider spend in the selected period."
        />
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
                whileHover={{ y: -3, transition: { duration: 0.2, ease: "easeOut" } }}
                className="glass-card rounded-card-lg border border-border-subtle p-5 cursor-pointer transition-shadow duration-base hover:shadow-elevated"
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

      {/* Comparison + Request Share */}
      <div className="grid gap-4 lg:grid-cols-2">
      <ChartCard
        title="Provider Comparison"
        subtitle="Side-by-side provider metrics"
        loading={providers.isLoading}
        empty={chartData.length === 0}
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
          <BarChart
            data={chartData}
            margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
            onMouseLeave={() => setHoveredBar(null)}
          >
            <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
            <XAxis dataKey="name" tick={{ fill: chrome.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
            <YAxis
              tick={{ fill: chrome.axis, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={metricFormatter}
              width={60}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(v: number) => metricFormatter(v)}
              itemStyle={{ color: chrome.text }}
              labelStyle={{ color: chrome.axis }}
              cursor={{ fill: "rgb(var(--color-brand) / 0.06)" }}
            />
            <Bar
              dataKey={metric}
              name={metricLabel}
              radius={[4, 4, 0, 0]}
              animationDuration={800}
              animationEasing="ease-out"
              onMouseEnter={(_, index) => setHoveredBar(index)}
            >
              {chartData.map((entry, i) => (
                <Cell
                  key={entry.provider}
                  fill={PROVIDER_COLORS[entry.provider] ?? chrome.primary}
                  opacity={hoveredBar === null || hoveredBar === i ? 1 : 0.35}
                  style={{ transition: "opacity 150ms ease-out" }}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <ChartCard
        title="Request Share"
        subtitle="Share of API calls by provider"
        loading={providers.isLoading}
        empty={chartData.length === 0}
        minHeight={300}
      >
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={chartData}
              dataKey="requests"
              nameKey="name"
              innerRadius={55}
              outerRadius={100}
              paddingAngle={2}
              animationDuration={800}
              animationEasing="ease-out"
            >
              {chartData.map((entry) => (
                <Cell key={entry.provider} fill={PROVIDER_COLORS[entry.provider] ?? chrome.primary} stroke="transparent" />
              ))}
            </Pie>
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(v: number) => formatNumber(v, true)}
              itemStyle={{ color: chrome.text }}
              labelStyle={{ color: chrome.axis }}
            />
          </PieChart>
        </ResponsiveContainer>
      </ChartCard>
      </div>

      {/* Provider catalog — connected providers show live data; the rest render
          as placeholders so the page reflects the full ecosystem without
          fabricating cost/usage numbers the backend doesn't track. */}
      {!providers.isLoading && (
        <Section title="More Providers" description="Additional integrations available to connect">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {PROVIDER_CATALOG.filter(
              (p) => !providerList.some((live) => live.provider.toLowerCase() === p.id),
            ).map((p) => (
              <div
                key={p.id}
                className="rounded-xl border border-dashed border-border-subtle p-4 flex flex-col items-center text-center gap-2 opacity-70 hover:opacity-100 transition-opacity duration-base"
              >
                <div
                  className="w-9 h-9 rounded-lg flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
                  style={{ background: p.color }}
                >
                  {p.name.slice(0, 2).toUpperCase()}
                </div>
                <span className="text-xs font-medium text-tx-secondary">{p.name}</span>
                <span className="badge bg-app-muted text-tx-muted text-[9px]">Not connected</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Models by provider table */}
      <Section title="All Models" description="All active models across providers">
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
                      {Array.from({ length: 7 }, (_, j) => (
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
      </Section>
    </div>
  );
}
