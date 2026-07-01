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
  Legend,
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
} from "../lib/utils";
import { useUIStore } from "../stores/ui";
import type { Granularity } from "../types/api";

const TOOLTIP_STYLE = {
  backgroundColor: "#12121A",
  border: "1px solid #1E293B",
  borderRadius: 8,
  color: "#F8FAFC",
  fontSize: 12,
};

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
    <div style={TOOLTIP_STYLE} className="p-3 shadow-card-hover">
      <p className="text-tx-muted text-xs mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-xs">
          <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-tx-secondary capitalize">{p.name}:</span>
          <span className="text-tx-primary font-medium">
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
  const [granularity, setGranularity] = useState<Granularity>("daily");

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
                <stop offset="5%" stopColor="#28E0C2" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#28E0C2" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: "#475569", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: "#475569", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatCost(v, currency, true)}
              width={56}
            />
            <Tooltip content={<CustomTooltip currency={currency} />} />
            <Area
              type="monotone"
              dataKey="total"
              name="Total"
              stroke="#28E0C2"
              strokeWidth={2}
              fill="url(#totalGrad)"
              dot={false}
              activeDot={{ r: 4, fill: "#28E0C2" }}
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
        >
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={95}
                paddingAngle={3}
                dataKey="value"
              >
                {pieData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={PROVIDER_COLORS[entry.name] ?? "#4F46E5"}
                    stroke="transparent"
                  />
                ))}
              </Pie>
              <Tooltip
                formatter={(v: number) => formatCost(v, currency, true)}
                contentStyle={TOOLTIP_STYLE}
              />
              <Legend
                formatter={(value: string) => (
                  <span style={{ color: "#94A3B8", fontSize: 12 }}>
                    {value.charAt(0).toUpperCase() + value.slice(1)}
                  </span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
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
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: "#475569", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => formatCost(v, currency, true)}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: "#94A3B8", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={90}
              />
              <Tooltip
                formatter={(v: number) => formatCost(v, currency, true)}
                contentStyle={TOOLTIP_STYLE}
              />
              <Bar dataKey="cost" name="Cost" fill="#4F46E5" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Recent Activity */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <div className="glass-card border border-border-subtle">
          <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle">
            <div>
              <h3 className="text-sm font-semibold text-tx-primary flex items-center gap-2">
                <Clock size={14} className="text-tx-muted" />
                Recent Activity
              </h3>
              <p className="text-xs text-tx-muted mt-0.5">Latest AI API calls across all providers</p>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
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
                  : events.map((e) => (
                      <tr key={e.id}>
                        <td className="text-tx-muted whitespace-nowrap">{formatDateTime(e.timestamp)}</td>
                        <td><ProviderBadge provider={e.provider} size="sm" /></td>
                        <td className="text-tx-primary font-mono text-xs">{modelDisplayName(e.model_id)}</td>
                        <td className="text-tx-secondary text-xs">{e.project_name}</td>
                        <td className="text-right font-mono text-xs">{formatNumber(e.input_tokens)}</td>
                        <td className="text-right font-mono text-xs">{formatNumber(e.output_tokens)}</td>
                        <td className="text-right font-semibold text-xs text-tx-primary">
                          {formatCost(e.cost, currency)}
                        </td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
