import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
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
import { motion, AnimatePresence } from "framer-motion";
import { DollarSign, Activity, Layers, Zap, Download, Radio, PlugZap, FolderPlus } from "lucide-react";
import MetricCard from "../components/MetricCard";
import ChartCard from "../components/ChartCard";
import LiveActivityFeed from "../components/LiveActivityFeed";
import CriticalAlertBanner from "../components/CriticalAlertBanner";
import { PROVIDER_COLORS } from "../lib/providerCatalog";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import { useOverview, useTimeSeries, useProviders, useModels } from "../hooks/useDashboard";
import { useLiveMetrics, useConnectionStatus } from "../realtime/hooks";
import { listProviderConnections, listProjectsCrud } from "../services/api";
import { useOrgStore } from "../stores/org";
import {
  formatCost,
  formatDate,
  formatTokens,
  formatNumber,
  modelDisplayName,
  providerDisplayName,
  cn,
} from "../utils";
import { useUIStore } from "../stores/ui";
import { useChartChrome } from "../lib/chartPalette";
import { toast } from "../stores/toast";
import type { Granularity } from "../types/api";

// EP-21.3 — replaces blank analytics with an actionable prompt for a
// brand-new organization that has neither a provider connection nor a
// project yet, reusing the same queries (and query keys — see
// features/Connections.tsx / Projects.tsx) the Connections and Projects
// pages already use, so this never drifts out of sync with their counts.
export function GettingStartedBanner() {
  const organizationId = useOrgStore((s) => s.organizationId);

  const connections = useQuery({
    queryKey: ["provider-connections", organizationId],
    queryFn: () => listProviderConnections(organizationId!),
    enabled: !!organizationId,
  });
  const projects = useQuery({
    queryKey: ["projects-crud", organizationId],
    queryFn: () => listProjectsCrud(organizationId!),
    enabled: !!organizationId,
  });

  if (connections.isLoading || projects.isLoading) return null;
  const hasConnections = (connections.data?.total ?? 0) > 0;
  const hasProjects = (projects.data?.total ?? 0) > 0;
  if (hasConnections && hasProjects) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-card-lg border border-border-subtle p-5 sm:p-6"
    >
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-tx-primary mb-1">Get set up to see real numbers here</h3>
          <p className="text-xs text-tx-muted leading-relaxed">
            Costs and usage appear as soon as a provider is connected and data starts flowing in.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 flex-shrink-0">
          {!hasConnections && (
            <Link to="/connections" className="btn-primary h-9 px-4 text-xs inline-flex items-center gap-1.5">
              <PlugZap size={14} /> Connect your first provider
            </Link>
          )}
          {!hasProjects && (
            <Link to="/projects" className="btn-outline h-9 px-4 text-xs inline-flex items-center gap-1.5">
              <FolderPlus size={14} /> Create your first project
            </Link>
          )}
        </div>
      </div>
    </motion.div>
  );
}

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
  const liveMetrics = useLiveMetrics();
  const connection = useConnectionStatus();

  const overview = useOverview();
  const timeSeries = useTimeSeries();
  const providers = useProviders();
  const models = useModels();

  const kpi = overview.data;
  const tsData = timeSeries.data?.data ?? [];
  const providerList = providers.data?.providers ?? [];
  const modelList = models.data?.models ?? [];

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

  const tokenChartData = tsData.slice(-14).map((d) => ({
    date: formatDate(d.date),
    tokens: d.total_tokens,
  }));

  const topModels = [...modelList]
    .sort((a, b) => parseFloat(b.total_cost) - parseFloat(a.total_cost))
    .slice(0, 8)
    .map((m) => ({
      name: modelDisplayName(m.model_id).slice(0, 14),
      cost: parseFloat(m.total_cost),
    }));

  const hasData = providerList.length > 0 || tsData.length > 0;

  function exportReport() {
    if (!hasData) {
      toast.warning("Nothing to export", "There is no spend data for the selected period.");
      return;
    }
    const lines: string[] = [];
    lines.push("COSTORAH Spend Report");
    lines.push(`Currency,${currency}`);
    if (kpi) {
      lines.push("");
      lines.push("Summary");
      lines.push("Metric,Value");
      lines.push(`Total Spend,${kpi.total_cost}`);
      lines.push(`Total Requests,${kpi.total_requests}`);
      lines.push(`Input Tokens,${kpi.total_input_tokens}`);
      lines.push(`Output Tokens,${kpi.total_output_tokens}`);
      lines.push(`Avg Cost / Request,${kpi.avg_cost_per_request}`);
      lines.push(`Active Providers,${kpi.active_providers}`);
      lines.push(`Active Models,${kpi.active_models}`);
    }
    lines.push("");
    lines.push("Spend by Provider");
    lines.push("Provider,Total Cost,Requests,Cost Share %");
    for (const p of providerList) {
      lines.push(`${providerDisplayName(p.provider)},${p.total_cost},${p.request_count},${p.cost_share_pct}`);
    }
    lines.push("");
    lines.push("Daily Spend");
    lines.push("Date,Total Cost,Total Tokens,Requests");
    for (const d of tsData) {
      lines.push(`${d.date},${d.total_cost},${d.total_tokens},${d.total_requests}`);
    }

    const csv = lines.join("\n");
    const a = document.createElement("a");
    a.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
    a.download = `costorah-report-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    toast.success("Report ready", "Spend report exported to CSV.");
  }

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader
        title="Overview"
        description="Real-time AI spend across every provider and project."
        actions={
          <button
            onClick={exportReport}
            disabled={overview.isLoading}
            className="btn-outline h-9 text-sm px-3.5"
          >
            <Download size={14} /> Export report
          </button>
        }
      />

      <CriticalAlertBanner />

      <GettingStartedBanner />

      {/* Live-update strip — appears once a usage.created event has landed
          since the socket connected; the KPI numbers below refresh via the
          normal query-invalidation path (see realtime/queryBridge.ts), this
          is just the "yes, something just happened" acknowledgment. */}
      <AnimatePresence>
        {connection.status === "connected" && liveMetrics.requestCount > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="flex items-center gap-2 text-xs text-tx-muted overflow-hidden"
          >
            <Radio size={12} className="text-brand flex-shrink-0" />
            <span>
              <span className="font-semibold text-tx-primary tabular-nums">
                +{formatNumber(liveMetrics.requestCount)}
              </span>{" "}
              request{liveMetrics.requestCount === 1 ? "" : "s"} ·{" "}
              <span className="font-semibold text-tx-primary tabular-nums">
                +{formatCost(liveMetrics.costDelta, currency, true)}
              </span>{" "}
              live since you opened this page
            </span>
          </motion.div>
        )}
      </AnimatePresence>

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
        empty={chartData.length === 0}
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
          empty={pieData.length === 0}
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
                itemStyle={{ color: chrome.text }}
                labelStyle={{ color: chrome.text }}
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
          empty={topModels.length === 0}
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
                itemStyle={{ color: chrome.text }}
                labelStyle={{ color: chrome.text }}
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

      {/* Token Throughput */}
      <ChartCard
        title="Token Throughput"
        subtitle="Daily token volume across all providers"
        loading={timeSeries.isLoading}
        empty={tokenChartData.length === 0}
        minHeight={220}
      >
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={tokenChartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: chrome.axis, fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: chrome.axis, fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => formatTokens(v)}
              width={48}
            />
            <Tooltip
              formatter={(v: number) => formatTokens(v)}
              contentStyle={tooltipStyle}
              itemStyle={{ color: chrome.text }}
              labelStyle={{ color: chrome.text }}
              cursor={{ fill: "rgb(var(--color-brand) / 0.06)" }}
            />
            <Bar dataKey="tokens" name="Tokens" fill={chrome.brand} radius={[4, 4, 0, 0]} animationDuration={800} animationEasing="ease-out" />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Per-provider quick stats */}
      <Section title="Provider Snapshot" description={`${formatNumber(kpi?.total_requests ?? 0)} total requests in the current period`}>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-6">
          {providers.isLoading
            ? Array.from({ length: 6 }, (_, i) => (
                <div key={i} className="rounded-xl border border-border-subtle p-3 h-[72px] skeleton" />
              ))
            : providerList.map((p) => (
                <motion.div
                  key={p.provider}
                  whileHover={{ y: -2 }}
                  className="rounded-xl border border-border-subtle bg-app-bg p-3 transition-shadow duration-base hover:shadow-card"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ background: PROVIDER_COLORS[p.provider] ?? chrome.primary }}
                    />
                    <span className="truncate text-xs font-medium text-tx-secondary">
                      {providerDisplayName(p.provider)}
                    </span>
                  </div>
                  <p className="mt-2 font-display text-base font-semibold text-tx-primary tabular-nums">
                    {formatNumber(p.request_count, true)}
                  </p>
                  <p className="text-[10px] text-tx-muted">{p.cost_share_pct}% of spend</p>
                </motion.div>
              ))}
        </div>
      </Section>

      {/* Recent Activity — live over WebSocket, falls back to polling */}
      <LiveActivityFeed limit={10} />
    </div>
  );
}
