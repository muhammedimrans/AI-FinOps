import { useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from "recharts";
import { motion } from "framer-motion";
import { DollarSign, Activity, Layers, Zap, Clock } from "lucide-react";
import MetricCard from "../components/MetricCard";
import ChartCard from "../components/ChartCard";
import ProviderBadge, { PROVIDER_COLORS } from "../components/ProviderBadge";
import {
  useOverview,
  useTimeSeries,
  useProviders,
  useModels,
  useRecentActivity,
} from "../hooks/useDashboard";
import {
  formatCost,
  formatDate,
  formatTokens,
  formatNumber,
  formatDateTime,
  modelDisplayName,
  providerDisplayName,
  cn,
} from "../lib/utils";
import { useUIStore } from "../stores/ui";
import { useChartChrome } from "../lib/chartPalette";
import type { Granularity } from "../types/api";

interface TooltipPayloadEntry {
  dataKey?: string | number;
  color?: string;
  name?: string | number;
  value?: string | number;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string | number;
  currency: string;
}

function CustomTooltip({ active, payload, label, currency }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-card rounded-xl border-white/10 shadow-elevated p-3.5 min-w-[140px]">
      <p className="text-tx-muted text-[11px] uppercase tracking-wide mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color, boxShadow: `0 0 6px ${p.color}` }} />
          <span className="text-tx-secondary capitalize flex-1">{p.name}:</span>
          <span className="text-tx-primary font-semibold tabular-nums">
            {formatCost(p.value ?? 0, currency, true)}
          </span>
        </div>
      ))}
    </div>
  );
}

function GranularityTabs({
  value,
  onChange,
}: {
  value: Granularity;
  onChange: (v: Granularity) => void;
}) {
  const tabs: Granularity[] = ["daily", "weekly", "monthly"];
  return (
    <div className="flex items-center gap-1 bg-app-bg rounded-lg p-0.5">
      {tabs.map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-150 capitalize
            ${value === t ? "bg-app-card text-tx-primary shadow-card" : "text-tx-muted hover:text-tx-secondary"}`}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

export default function Overview() {
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
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const [hoveredProvider, setHoveredProvider] = useState<string | null>(null);
  const [hoveredBar, setHoveredBar] = useState<number | null>(null);

  const overview = useOverview();
  const timeSeries = useTimeSeries();
  const providers = useProviders();
  const models = useModels();
  const activity = useRecentActivity(10);

  const kpi = overview.data;
  const tsData = timeSeries.data?.data ?? [];
  const providerList = providers.data?.providers ?? [];
  const modelList = models.data?.models ?? [];
  const events = activity.data?.events ?? [];

  // Sparklines derived from ts data (last 7 pts)
  const recent7 = tsData.slice(-7).map((d) => parseFloat(d.total_cost));

  const chartData = tsData.map((d) => ({
    date: formatDate(d.date),
    total: parseFloat(d.total_cost),
    ...Object.fromEntries(
      Object.entries(d.provider_breakdown).map(([k, v]) => [k, parseFloat(v)]),
    ),
  }));

  const pieData = providerList.map((p) => ({
    name: p.provider,
    value: parseFloat(p.total_cost),
  }));

  const topModels = [...modelList]
    .sort((a, b) => parseFloat(b.total_cost) - parseFloat(a.total_cost))
    .slice(0, 8)
    .map((m) => ({
      name: modelDisplayName(m.model_id).slice(0, 14),
      cost: parseFloat(m.total_cost),
    }));

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
          <MetricCard
            label="Total Spend"
            value={kpi?.total_cost ?? "0"}
            type="currency"
            currency={currency}
            trendPct={kpi?.cost_trend_pct}
            trendInverse={false}
            subtitle="vs previous period"
            icon={DollarSign}
            gradient="teal"
            sparkline={recent7}
            loading={overview.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <MetricCard
            label="Total Requests"
            value={kpi?.total_requests ?? 0}
            type="number"
            trendPct={kpi?.request_trend_pct}
            trendInverse={false}
            subtitle="API calls processed"
            icon={Activity}
            gradient="blue"
            sparkline={recent7.map((v, i) => i * 2000 + v * 10)}
            loading={overview.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <MetricCard
            label="Token Usage"
            value={formatTokens((kpi?.total_input_tokens ?? 0) + (kpi?.total_output_tokens ?? 0))}
            type="raw"
            trendPct={kpi?.token_trend_pct}
            subtitle={`${formatTokens(kpi?.total_input_tokens ?? 0)} in · ${formatTokens(kpi?.total_output_tokens ?? 0)} out`}
            icon={Layers}
            gradient="emerald"
            loading={overview.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <MetricCard
            label="Avg Cost / Request"
            value={kpi?.avg_cost_per_request ?? "0"}
            type="currency"
            currency={currency}
            subtitle={`${kpi?.active_providers ?? 0} providers · ${kpi?.active_models ?? 0} models`}
            icon={Zap}
            gradient="purple"
            loading={overview.isLoading}
          />
        </motion.div>
      </div>

      {/* Cost Trend Chart */}
      <ChartCard
        title="Spend Trend"
        subtitle="Total AI spending over time with provider breakdown"
        loading={timeSeries.isLoading}
        error={timeSeries.error ? "Failed to load" : null}
        actions={
          <GranularityTabs
            value={granularity}
            onChange={(g) => {
              setGranularity(g);
              useUIStore.getState().setGranularity(g);
            }}
          />
        }
        minHeight={300}
      >
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="totalGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={chrome.brand} stopOpacity={0.3} />
                <stop offset="95%" stopColor={chrome.brand} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: chrome.axis, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: chrome.axis, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatCost(v, currency, true)}
              width={56}
            />
            <Tooltip content={<CustomTooltip currency={currency} />} cursor={{ stroke: chrome.brand, strokeWidth: 1, strokeDasharray: "3 3" }} />
            <Area
              type="monotone"
              dataKey="total"
              name="Total"
              stroke={chrome.brand}
              strokeWidth={2.5}
              fill="url(#totalGrad)"
              dot={false}
              activeDot={{ r: 5, fill: chrome.brand, stroke: chrome.bg, strokeWidth: 2 }}
              animationDuration={1000}
              animationEasing="ease-out"
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Provider + Model charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <ChartCard
          title="Provider Distribution"
          subtitle="Cost share by provider"
          loading={providers.isLoading}
          minHeight={260}
          bodyClassName="flex flex-col sm:flex-row items-center gap-2"
        >
          <div className="w-full sm:w-3/5">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={95}
                paddingAngle={3}
                dataKey="value"
                animationDuration={900}
                animationEasing="ease-out"
              >
                {pieData.map((entry) => {
                  const dimmed = hoveredProvider !== null && hoveredProvider !== entry.name;
                  return (
                    <Cell
                      key={entry.name}
                      fill={PROVIDER_COLORS[entry.name] ?? chrome.primary}
                      stroke="transparent"
                      opacity={dimmed ? 0.3 : 1}
                      style={{ transition: "opacity 150ms ease-out" }}
                      onMouseEnter={() => setHoveredProvider(entry.name)}
                      onMouseLeave={() => setHoveredProvider(null)}
                    />
                  );
                })}
              </Pie>
              <Tooltip
                formatter={(v: number) => formatCost(v, currency, true)}
                contentStyle={tooltipStyle}
              />
            </PieChart>
          </ResponsiveContainer>
          </div>

          {/* Interactive legend — hover highlights the matching slice */}
          <div className="flex sm:flex-col flex-wrap gap-2 sm:gap-1.5 sm:w-2/5 px-2">
            {pieData.map((entry) => {
              const total = pieData.reduce((s, p) => s + p.value, 0);
              const pct = total > 0 ? (entry.value / total) * 100 : 0;
              const dimmed = hoveredProvider !== null && hoveredProvider !== entry.name;
              return (
                <button
                  key={entry.name}
                  onMouseEnter={() => setHoveredProvider(entry.name)}
                  onMouseLeave={() => setHoveredProvider(null)}
                  className={cn(
                    "flex items-center gap-2 text-left px-2 py-1.5 rounded-lg transition-all duration-fast",
                    dimmed ? "opacity-40" : "opacity-100 bg-app-hover/60",
                  )}
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ background: PROVIDER_COLORS[entry.name] ?? chrome.primary }}
                  />
                  <span className="text-xs text-tx-secondary flex-1 truncate">
                    {providerDisplayName(entry.name)}
                  </span>
                  <span className="text-xs font-semibold text-tx-primary tabular-nums">
                    {pct.toFixed(0)}%
                  </span>
                </button>
              );
            })}
          </div>
        </ChartCard>

        <ChartCard
          title="Top Models by Spend"
          subtitle="Highest cost AI models"
          loading={models.isLoading}
          minHeight={260}
        >
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={topModels}
              layout="vertical"
              margin={{ top: 0, right: 16, bottom: 0, left: 4 }}
              onMouseLeave={() => setHoveredBar(null)}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: chrome.axis, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => formatCost(v, currency, true)}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: chrome.axis, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={90}
              />
              <Tooltip
                formatter={(v: number) => formatCost(v, currency, true)}
                contentStyle={tooltipStyle}
                cursor={{ fill: "rgb(var(--color-brand) / 0.06)" }}
              />
              <Bar
                dataKey="cost"
                name="Cost"
                radius={[0, 4, 4, 0]}
                animationDuration={800}
                animationEasing="ease-out"
                onMouseEnter={(_, index) => setHoveredBar(index)}
              >
                {topModels.map((entry, i) => (
                  <Cell
                    key={entry.name}
                    fill={hoveredBar === null || hoveredBar === i ? "rgb(var(--color-brand))" : "rgb(var(--color-brand) / 0.35)"}
                    style={{ transition: "fill 150ms ease-out" }}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Recent Activity */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <div className="glass-card rounded-card-lg border border-border-subtle relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand/40 to-transparent" aria-hidden="true" />
          <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
            <div>
              <h3 className="text-sm font-semibold text-tx-primary flex items-center gap-2">
                <Clock size={14} className="text-tx-muted" />
                Recent Activity
              </h3>
              <p className="text-xs text-tx-muted mt-0.5">Latest AI API calls across all providers</p>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="relative flex w-2 h-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75" />
                <span className="relative inline-flex rounded-full w-2 h-2 bg-success" />
              </span>
              <span className="text-xs text-tx-muted">Live</span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Provider</th>
                  <th>Model</th>
                  <th>Project</th>
                  <th className="text-right">Tokens In</th>
                  <th className="text-right">Tokens Out</th>
                  <th className="text-right">Cost</th>
                </tr>
              </thead>
              <tbody>
                {activity.isLoading
                  ? Array.from({ length: 6 }, (_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 7 }, (_, j) => (
                          <td key={j}><div className="h-4 skeleton rounded w-full" /></td>
                        ))}
                      </tr>
                    ))
                  : events.map((e, i) => (
                      <motion.tr
                        key={e.id}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.25, delay: Math.min(i * 0.04, 0.3) }}
                      >
                        <td className="text-tx-muted whitespace-nowrap">{formatDateTime(e.timestamp)}</td>
                        <td><ProviderBadge provider={e.provider} size="sm" /></td>
                        <td className="text-tx-primary font-mono text-xs">{modelDisplayName(e.model_id)}</td>
                        <td className="text-tx-secondary text-xs">{e.project_name}</td>
                        <td className="text-right font-mono text-xs">{formatNumber(e.input_tokens)}</td>
                        <td className="text-right font-mono text-xs">{formatNumber(e.output_tokens)}</td>
                        <td className="text-right font-semibold text-xs text-tx-primary">
                          {formatCost(e.cost, currency)}
                        </td>
                      </motion.tr>
                    ))}
              </tbody>
            </table>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
