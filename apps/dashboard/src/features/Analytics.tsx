import { useState, useMemo, useEffect } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type PaginationState,
} from "@tanstack/react-table";
import { motion } from "framer-motion";
import { Search, ArrowUpDown, ArrowUp, ArrowDown, Download, DollarSign, Gauge, TrendingDown, TrendingUp, AlertTriangle, Sparkles, Flame, FolderKanban, X, Info } from "lucide-react";
import ChartCard from "../components/ChartCard";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import MetricCard from "../components/MetricCard";
import ProviderBadge from "../components/ProviderBadge";
import ProviderLogo from "../components/ProviderLogo";
import { PROVIDER_COLORS, CONNECTABLE_PROVIDERS, parseOpenRouterModelId, hasKnownUsageApi } from "../lib/providerCatalog";
import { useTimeSeries, useModels, useProviders, useProjects, useHeatmap } from "../hooks/useDashboard";
import { linearForecast, detectAnomalies } from "../lib/insights";
import { formatCost, formatDate, formatNumber, formatTokens, modelDisplayName, providerDisplayName } from "../utils";
import { useUIStore } from "../stores/ui";
import { useOrgStore } from "../stores/org";
import { useChartChrome } from "../lib/chartPalette";
import { toast } from "../stores/toast";
import { getSchedulerStatus, listProviderConnections } from "../services/api";
import { useOnboardingWidgetStore } from "../stores/onboardingWidget";
import type { Granularity, ModelSummary, ProjectCost } from "../types/api";

const columnHelper = createColumnHelper<ModelSummary & { rank: number }>();
const projectColumnHelper = createColumnHelper<ProjectCost & { rank: number }>();

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

type ExportFormat = "spend" | "providers" | "projects" | "models";

export default function Analytics() {
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
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([{ id: "total_cost", desc: true }]);
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 });
  const [exportFormat, setExportFormat] = useState<ExportFormat>("models");

  // EP-25.4.4 Part 2 — marks the dashboard's "View Analytics" onboarding
  // step complete the moment this page is actually opened, persisted so
  // it survives reloads (see stores/onboardingWidget.ts's own header
  // comment for why this is a real, tracked signal rather than a mirror
  // of "usage exists").
  const markVisitedAnalytics = useOnboardingWidgetStore((s) => s.markVisitedAnalytics);
  useEffect(() => {
    markVisitedAnalytics();
  }, [markVisitedAnalytics]);

  // EP-24.1 — dimension filters (Project / Provider / Model). Organization
  // is already the implicit scope of every query (useOrgStore) and Date
  // Range is the existing top-bar date picker (useUIStore) — both already
  // filter every chart on this page; these three add the remaining ones
  // the spec names, threaded straight through to the now filter-aware
  // dashboard endpoints.
  const [projectFilter, setProjectFilter] = useState<string>("");
  const [providerFilter, setProviderFilter] = useState<string>("");
  const [modelFilter, setModelFilter] = useState<string>("");
  const filters = useMemo(() => {
    const f: { project_id?: string; provider?: string; model?: string } = {};
    if (projectFilter) f.project_id = projectFilter;
    if (providerFilter) f.provider = providerFilter;
    if (modelFilter) f.model = modelFilter;
    return f;
  }, [projectFilter, providerFilter, modelFilter]);
  const hasActiveFilters = !!(projectFilter || providerFilter || modelFilter);

  const timeSeries = useTimeSeries(filters);
  const models = useModels(filters);
  const providers = useProviders(filters);
  const projects = useProjects(filters);
  const heatmap = useHeatmap(filters);
  // Unfiltered project list purely to populate the Project filter dropdown
  // — selecting a provider/model filter shouldn't also shrink which
  // projects appear as selectable options.
  const allProjects = useProjects();
  // Unfiltered model list purely to populate the Model filter dropdown —
  // same reasoning as allProjects above.
  const allModelsQuery = useModels();

  // EP-24.1 — Real-Time Updates: reuse the EP-23.4 background scheduler as
  // the source of fresh data, exactly like Connections.tsx's
  // AutoSyncStatusSection already does — poll scheduler status and
  // invalidate this page's queries the moment a background sync
  // completes, rather than building a second live-update pipeline.
  const organizationId = useOrgStore((s) => s.organizationId);
  const queryClient = useQueryClient();
  const schedulerStatus = useQuery({
    queryKey: ["scheduler-status", organizationId],
    queryFn: () => getSchedulerStatus(organizationId!),
    enabled: !!organizationId,
    refetchInterval: 20_000,
  });
  const [lastSeenJobId, setLastSeenJobId] = useState<string | null>(null);
  useEffect(() => {
    const job = schedulerStatus.data?.current_job;
    if (!job) return;
    const finished = job.status === "completed" || job.status === "failed";
    if (!finished || job.job_id === lastSeenJobId) return;
    setLastSeenJobId(job.job_id);
    for (const key of ["overview", "time-series", "providers", "models", "projects", "heatmap", "activity-feed"]) {
      void queryClient.invalidateQueries({ queryKey: [key, organizationId] });
    }
  }, [schedulerStatus.data, lastSeenJobId, organizationId, queryClient]);

  // EP-26.0.3.3 — same shared query key Providers.tsx/Models.tsx/
  // useDashboardState already use (never a second, out-of-sync fetch) so
  // an empty "Spend by Provider" chart can distinguish "nothing connected"
  // from "connected, but this provider has no bulk usage-history API" —
  // the latter must never look like an error or an indefinite wait.
  const connections = useQuery({
    queryKey: ["provider-connections", organizationId],
    queryFn: () => listProviderConnections(organizationId!),
    enabled: !!organizationId,
  });
  const connectionList = connections.data?.connections ?? [];
  const hasUsageIncapableConnection =
    connectionList.length > 0 && connectionList.every((c) => !hasKnownUsageApi(c.provider_type));

  // Providers present in the time series — derived from the data rather than a
  // hardcoded list so every provider the backend reports gets a chart series.
  const seriesProviders = useMemo(() => {
    const keys = new Set<string>();
    for (const d of timeSeries.data?.data ?? []) {
      for (const k of Object.keys(d.provider_breakdown)) keys.add(k);
    }
    return [...keys].sort();
  }, [timeSeries.data]);

  const chartData = (timeSeries.data?.data ?? []).map((d) => ({
    date: formatDate(d.date),
    ...Object.fromEntries(
      seriesProviders.map((p) => [p, parseFloat(d.provider_breakdown[p] ?? "0")]),
    ),
    total: parseFloat(d.total_cost),
  }));

  const providerCompareData = (providers.data?.providers ?? []).map((p) => ({
    provider: p.provider,
    name: providerDisplayName(p.provider),
    cost: parseFloat(p.total_cost),
    requests: p.request_count / 1000,
  }));

  // Weekly-aggregated cost, derived client-side from the daily time series —
  // no dedicated weekly-granularity data is fetched for this view.
  const weeklyTrendData = useMemo(() => {
    const points = timeSeries.data?.data ?? [];
    const weeks: { week: string; cost: number }[] = [];
    for (let i = 0; i < points.length; i += 7) {
      const chunk = points.slice(i, i + 7);
      const cost = chunk.reduce((s, d) => s + parseFloat(d.total_cost), 0);
      weeks.push({ week: `Week ${weeks.length + 1}`, cost });
    }
    return weeks;
  }, [timeSeries.data]);

  // EP-24.1 — Token Trend: input/output/total tokens per day, sourced from
  // the same time-series points whose prompt_tokens/completion_tokens
  // fields the backend now populates (UsageCostRecordRepository.get_daily_trend).
  const tokenTrendData = (timeSeries.data?.data ?? []).map((d) => ({
    date: formatDate(d.date),
    input: d.input_tokens,
    output: d.output_tokens,
    total: d.total_tokens,
  }));

  // EP-24.1 — Usage Heatmap: hour-of-day (0-23) x day-of-week (0=Sun..6=Sat)
  // cost-weighted grid, sourced directly from GET /v1/dashboard/heatmap —
  // no client-side bucketing of raw events.
  const heatmapCells = useMemo(() => heatmap.data?.cells ?? [], [heatmap.data]);
  const heatmapMax = Math.max(1, ...heatmapCells.map((c) => parseFloat(c.total_cost)));
  const heatmapByCell = useMemo(() => {
    const map = new Map<string, (typeof heatmapCells)[number]>();
    for (const c of heatmapCells) map.set(`${c.day_of_week}-${c.hour_of_day}`, c);
    return map;
  }, [heatmapCells]);

  // EP-24.1 — Project Spend ranking, sourced from the same filter-aware
  // GET /v1/dashboard/projects endpoint the Projects page's management
  // section already calls.
  const projectTableData = useMemo(
    () =>
      (projects.data?.projects ?? [])
        .sort((a, b) => parseFloat(b.total_cost) - parseFloat(a.total_cost))
        .map((p, i) => ({ ...p, rank: i + 1 })),
    [projects.data],
  );

  const projectColumns = useMemo(
    () => [
      projectColumnHelper.accessor("rank", {
        header: "#",
        size: 40,
        cell: (info) => <span className="text-tx-muted text-xs">{info.getValue()}</span>,
      }),
      projectColumnHelper.accessor("project_name", {
        header: "Project",
        cell: (info) => <span className="text-xs font-medium text-tx-primary">{info.getValue()}</span>,
      }),
      projectColumnHelper.accessor("total_cost", {
        header: "Cost",
        cell: (info) => (
          <span className="font-semibold text-tx-primary text-xs">
            {formatCost(info.getValue(), currency, true)}
          </span>
        ),
      }),
      projectColumnHelper.accessor("request_count", {
        header: "Requests",
        cell: (info) => <span className="font-mono text-xs">{formatNumber(info.getValue())}</span>,
      }),
      projectColumnHelper.accessor("budget", {
        header: "Budget",
        cell: (info) => {
          const v = info.getValue();
          return <span className="font-mono text-xs text-tx-muted">{v != null ? formatCost(v, currency, true) : "—"}</span>;
        },
      }),
    ],
    [currency],
  );

  const projectTable = useReactTable({
    data: projectTableData,
    columns: projectColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  // ── In-app spend intelligence (computed from the real daily series) ────────
  const dailySeries = useMemo(
    () =>
      (timeSeries.data?.data ?? []).map((d) => ({
        date: d.date,
        value: parseFloat(d.total_cost),
      })),
    [timeSeries.data],
  );

  const forecast = useMemo(() => linearForecast(dailySeries, 14), [dailySeries]);

  const forecastChartData = useMemo(() => {
    if (!forecast) return [];
    const actual = dailySeries.map((p) => ({ date: formatDate(p.date), actual: p.value }));
    const last = actual[actual.length - 1]!;
    return [
      ...actual.slice(0, -1),
      // Bridge point: the last actual day carries both keys so the dashed
      // projection visually connects to the solid line.
      { ...last, projected: last.actual },
      ...forecast.points.map((p) => ({ date: formatDate(p.date), projected: p.value })),
    ];
  }, [dailySeries, forecast]);

  const anomalies = useMemo(
    () => detectAnomalies(dailySeries, { window: 7, threshold: 2 }).slice(-8).reverse(),
    [dailySeries],
  );

  const tableData = useMemo(
    () =>
      (models.data?.models ?? [])
        .sort((a, b) => parseFloat(b.total_cost) - parseFloat(a.total_cost))
        .map((m, i) => ({ ...m, rank: i + 1 })),
    [models.data],
  );

  const columns = useMemo(
    () => [
      columnHelper.accessor("rank", {
        header: "#",
        size: 40,
        cell: (info) => <span className="text-tx-muted text-xs">{info.getValue()}</span>,
      }),
      columnHelper.accessor("provider", {
        header: "Provider",
        cell: (info) => (
          <div className="flex items-center gap-1.5">
            <ProviderLogo providerId={info.getValue()} size="xs" />
            <ProviderBadge provider={info.getValue()} size="sm" />
          </div>
        ),
      }),
      columnHelper.accessor("model_id", {
        header: "Model",
        cell: (info) => {
          // EP-26.0.1: OpenRouter's model_id is a "vendor/model" slug
          // (e.g. "anthropic/claude-sonnet-4") — a first-class provider in
          // its own right, so this shows the underlying vendor + model
          // rather than pretending the request belongs directly to that
          // vendor (CLAUDE.md's EP-26.0.1 Part 5). Every other provider's
          // model_id is unaffected — parseOpenRouterModelId only applies
          // when provider === "openrouter". EP-26.0.4 additionally shows
          // the underlying vendor's own logo, so "OpenRouter -> Claude ->
          // Claude Sonnet 4" is never confused with a direct Anthropic
          // connection despite sharing the same visual identity element.
          if (info.row.original.provider === "openrouter") {
            const parsed = parseOpenRouterModelId(info.getValue());
            if (parsed) {
              return (
                <span className="flex items-center gap-1.5 font-mono text-xs text-tx-primary">
                  <ProviderLogo providerId={parsed.vendorSlug} size="xs" bare />
                  <span className="text-tx-muted">{parsed.vendorLabel}</span>{" "}
                  {modelDisplayName(parsed.modelSlug)}
                </span>
              );
            }
          }
          return (
            <span className="font-mono text-xs text-tx-primary">{modelDisplayName(info.getValue())}</span>
          );
        },
      }),
      columnHelper.accessor("request_count", {
        header: "Requests",
        cell: (info) => <span className="font-mono text-xs">{formatNumber(info.getValue())}</span>,
      }),
      columnHelper.accessor("input_tokens", {
        header: "In Tokens",
        cell: (info) => <span className="font-mono text-xs">{formatTokens(info.getValue())}</span>,
      }),
      columnHelper.accessor("output_tokens", {
        header: "Out Tokens",
        cell: (info) => <span className="font-mono text-xs">{formatTokens(info.getValue())}</span>,
      }),
      columnHelper.accessor("cost_per_1k_tokens", {
        header: "$/1K Tokens",
        cell: (info) => (
          <span className="font-mono text-xs">{formatCost(info.getValue(), currency)}</span>
        ),
      }),
      columnHelper.accessor("total_cost", {
        header: "Total Cost",
        cell: (info) => (
          <span className="font-semibold text-tx-primary text-xs">
            {formatCost(info.getValue(), currency, true)}
          </span>
        ),
      }),
    ],
    [currency],
  );

  const table = useReactTable({
    data: tableData,
    columns,
    state: { sorting, globalFilter: search, pagination },
    onSortingChange: setSorting,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  // Summary stats
  const allModels = models.data?.models ?? [];
  const totalCost = allModels.reduce((s, m) => s + parseFloat(m.total_cost), 0);
  const avgCost = allModels.length
    ? allModels.reduce((s, m) => s + parseFloat(m.avg_cost_per_request), 0) / allModels.length
    : 0;
  const minCost = allModels.length
    ? Math.min(...allModels.map((m) => parseFloat(m.avg_cost_per_request)))
    : 0;
  const maxCost = allModels.length
    ? Math.max(...allModels.map((m) => parseFloat(m.avg_cost_per_request)))
    : 0;

  // EP-24.1 — CSV export generalized to Spend/Providers/Projects/Models
  // (was Models-only). Each format reuses data already fetched for the
  // page's own charts/tables — no separate export-specific query.
  function exportCSV() {
    let header: string;
    let rows: string[];
    let count: number;
    let label: string;

    if (exportFormat === "spend") {
      const points = timeSeries.data?.data ?? [];
      header = "Date,Total Cost,Total Tokens,Requests";
      rows = points.map((d) => [d.date, d.total_cost, d.total_tokens, d.total_requests].join(","));
      count = points.length;
      label = "daily spend points";
    } else if (exportFormat === "providers") {
      const list = providers.data?.providers ?? [];
      header = "Provider,Total Cost,Requests,Models,Input Tokens,Output Tokens,Cost Share %";
      rows = list.map((p) =>
        [
          p.provider,
          p.total_cost,
          p.request_count,
          p.model_count,
          p.input_tokens,
          p.output_tokens,
          p.cost_share_pct,
        ].join(","),
      );
      count = list.length;
      label = "providers";
    } else if (exportFormat === "projects") {
      header = "Project,Total Cost,Requests,Budget,Budget Utilization %";
      rows = projectTableData.map((p) =>
        [p.project_name, p.total_cost, p.request_count, p.budget ?? "", p.budget_utilization_pct ?? ""].join(","),
      );
      count = projectTableData.length;
      label = "projects";
    } else {
      header = "Provider,Model,Requests,Input Tokens,Output Tokens,Total Cost";
      rows = tableData.map((m) =>
        [m.provider, m.model_id, m.request_count, m.input_tokens, m.output_tokens, m.total_cost].join(","),
      );
      count = tableData.length;
      label = "models";
    }

    if (count === 0) {
      toast.warning("Nothing to export", `There is no ${label} data for the current period.`);
      return;
    }
    const csv = [header, ...rows].join("\n");
    const a = document.createElement("a");
    a.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
    a.download = `costorah-${exportFormat}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    toast.success("Export ready", `${count} ${label} exported to CSV.`);
  }

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader title="Cost Analytics" description="Break down spend trends and model-level cost efficiency." />

      {/* EP-24.1 — Filters: Date Range and Organization are already the
          page's implicit scope (top-bar date picker + active org); Project/
          Provider/Model narrow every chart and table below via the same
          filter-aware endpoints. */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={projectFilter}
          onChange={(e) => setProjectFilter(e.target.value)}
          aria-label="Filter by project"
          className="bg-app-bg border border-border-subtle rounded-lg px-2.5 py-1.5 text-xs text-tx-secondary focus:outline-none focus:border-brand"
        >
          <option value="">All projects</option>
          {(allProjects.data?.projects ?? []).map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.project_name}
            </option>
          ))}
        </select>
        <select
          value={providerFilter}
          onChange={(e) => setProviderFilter(e.target.value)}
          aria-label="Filter by provider"
          className="bg-app-bg border border-border-subtle rounded-lg px-2.5 py-1.5 text-xs text-tx-secondary focus:outline-none focus:border-brand"
        >
          <option value="">All providers</option>
          {CONNECTABLE_PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <select
          value={modelFilter}
          onChange={(e) => setModelFilter(e.target.value)}
          aria-label="Filter by model"
          className="bg-app-bg border border-border-subtle rounded-lg px-2.5 py-1.5 text-xs text-tx-secondary focus:outline-none focus:border-brand"
        >
          <option value="">All models</option>
          {(allModelsQuery.data?.models ?? []).map((m) => (
            <option key={m.model_id} value={m.model_id}>
              {modelDisplayName(m.model_id)}
            </option>
          ))}
        </select>
        {hasActiveFilters && (
          <button
            onClick={() => {
              setProjectFilter("");
              setProviderFilter("");
              setModelFilter("");
            }}
            className="btn-ghost h-7 px-2.5 text-[11px] inline-flex items-center gap-1"
          >
            <X size={11} /> Clear filters
          </button>
        )}
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}>
          <MetricCard
            label="Total Spend"
            value={totalCost}
            type="currency"
            currency={currency}
            subtitle="all providers"
            icon={DollarSign}
            gradient="teal"
            loading={models.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <MetricCard
            label="Avg Cost/Request"
            value={avgCost}
            type="currency"
            currency={currency}
            subtitle="across models"
            icon={Gauge}
            gradient="blue"
            loading={models.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <MetricCard
            label="Min Cost/Request"
            value={minCost}
            type="currency"
            currency={currency}
            subtitle="cheapest model"
            icon={TrendingDown}
            gradient="emerald"
            loading={models.isLoading}
          />
        </motion.div>
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
          <MetricCard
            label="Max Cost/Request"
            value={maxCost}
            type="currency"
            currency={currency}
            subtitle="premium model"
            icon={TrendingUp}
            gradient="purple"
            loading={models.isLoading}
          />
        </motion.div>
      </div>

      {/* Stacked Area Chart */}
      <ChartCard
        title="Spend by Provider"
        subtitle="Stacked area chart showing daily cost breakdown"
        loading={timeSeries.isLoading}
        empty={chartData.length === 0}
        emptyContent={
          hasUsageIncapableConnection ? (
            <div className="flex flex-col items-center text-center px-6 max-w-sm">
              <div className="w-10 h-10 rounded-xl bg-info-dim flex items-center justify-center mb-3">
                <Info size={18} className="text-info" />
              </div>
              <p className="text-sm font-medium text-tx-primary mb-0.5">
                {connectionList[0]?.display_name ?? "Your provider"} is connected successfully.
              </p>
              <p className="text-xs text-tx-muted leading-relaxed mb-4">
                Historical usage cannot be imported from this provider — that&apos;s expected, not an
                error. Use AI Playground to generate tracked requests and populate this chart.
              </p>
              <Link to="/playground" className="btn-outline h-8 px-3.5 text-xs">
                Open AI Playground
              </Link>
            </div>
          ) : undefined
        }
        minHeight={300}
        actions={
          <div className="flex gap-1 bg-app-bg rounded-lg p-0.5">
            {(["daily", "weekly", "monthly"] as Granularity[]).map((g) => (
              <button
                key={g}
                onClick={() => {
                  setGranularity(g);
                  useUIStore.getState().setGranularity(g);
                }}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all capitalize
                  ${granularity === g ? "bg-app-card text-tx-primary shadow-card" : "text-tx-muted hover:text-tx-secondary"}`}
              >
                {g}
              </button>
            ))}
          </div>
        }
      >
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <defs>
              {seriesProviders.map((p) => (
                <linearGradient key={p} id={`grad-${p}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={PROVIDER_COLORS[p]} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={PROVIDER_COLORS[p]} stopOpacity={0} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
            <XAxis dataKey="date" tick={{ fill: chrome.axis, fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fill: chrome.axis, fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v: number) => formatCost(v, currency, true)} width={56} />
            <Tooltip
              contentStyle={tooltipStyle}
              itemStyle={{ color: chrome.text }}
              labelStyle={{ color: chrome.text }}
              formatter={(v: number) => formatCost(v, currency, true)}
            />
            <Legend formatter={(v: string) => <span style={{ color: chrome.axis, fontSize: 12, textTransform: "capitalize" }}>{v}</span>} />
            {seriesProviders.map((p) => (
              <Area
                key={p}
                type="monotone"
                dataKey={p}
                name={p}
                stackId="1"
                stroke={PROVIDER_COLORS[p]}
                fill={`url(#grad-${p})`}
                strokeWidth={1.5}
                dot={false}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Provider Comparison + Weekly Trend */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard
          title="Provider Comparison"
          subtitle="Cost vs. request volume by provider"
          loading={providers.isLoading}
          empty={providerCompareData.length === 0}
          minHeight={280}
        >
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={providerCompareData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
              <XAxis dataKey="name" tick={{ fill: chrome.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: chrome.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={48} />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: chrome.text }}
                labelStyle={{ color: chrome.text }}
                formatter={(v: number, name: string) =>
                  name === "requests" ? [`${formatNumber(v * 1000, true)}`, "Requests"] : [formatCost(v, currency, true), "Cost"]
                }
              />
              <Legend formatter={(v: string) => <span style={{ color: chrome.axis, fontSize: 12, textTransform: "capitalize" }}>{v === "requests" ? "Requests (K)" : v}</span>} />
              <Bar dataKey="cost" name="cost" radius={[4, 4, 0, 0]}>
                {providerCompareData.map((entry) => (
                  <Cell key={entry.provider} fill={PROVIDER_COLORS[entry.provider] ?? chrome.primary} />
                ))}
              </Bar>
              <Bar dataKey="requests" name="requests" fill={chrome.grid} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Weekly Trend"
          subtitle="Cost aggregated into 7-day windows"
          loading={timeSeries.isLoading}
          empty={weeklyTrendData.length === 0}
          minHeight={280}
        >
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={weeklyTrendData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
              <XAxis dataKey="week" tick={{ fill: chrome.axis, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fill: chrome.axis, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => formatCost(v, currency, true)}
                width={48}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: chrome.text }}
                labelStyle={{ color: chrome.text }}
                formatter={(v: number) => formatCost(v, currency, true)}
              />
              <Line type="monotone" dataKey="cost" stroke={chrome.brand} strokeWidth={2.5} dot={{ r: 3, fill: chrome.brand }} animationDuration={800} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* EP-24.1 — Token Trend: input/output/total tokens per day */}
      <ChartCard
        title="Token Trend"
        subtitle="Input, output, and total token usage over time"
        loading={timeSeries.isLoading}
        empty={tokenTrendData.length === 0}
        minHeight={260}
      >
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={tokenTrendData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="inputGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={chrome.brand} stopOpacity={0.3} />
                <stop offset="95%" stopColor={chrome.brand} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="outputGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={chrome.primary} stopOpacity={0.3} />
                <stop offset="95%" stopColor={chrome.primary} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
            <XAxis dataKey="date" tick={{ fill: chrome.axis, fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fill: chrome.axis, fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v: number) => formatTokens(v)} width={52} />
            <Tooltip
              contentStyle={tooltipStyle}
              itemStyle={{ color: chrome.text }}
              labelStyle={{ color: chrome.text }}
              formatter={(v: number, name: string) => [formatTokens(v), name === "input" ? "Input" : name === "output" ? "Output" : "Total"]}
            />
            <Legend formatter={(v: string) => <span style={{ color: chrome.axis, fontSize: 12, textTransform: "capitalize" }}>{v}</span>} />
            <Area type="monotone" dataKey="input" name="input" stackId="tok" stroke={chrome.brand} fill="url(#inputGrad)" strokeWidth={1.5} dot={false} />
            <Area type="monotone" dataKey="output" name="output" stackId="tok" stroke={chrome.primary} fill="url(#outputGrad)" strokeWidth={1.5} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Forecast + anomalies — computed in-app from the real daily series */}
      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <ChartCard
          title="Spend Forecast"
          subtitle={
            forecast
              ? `Linear trend fit to the visible period, projected 14 days — computed in-app, ${forecast.dailySlope >= 0 ? "+" : "−"}${formatCost(Math.abs(forecast.dailySlope), currency, true)}/day`
              : "Linear trend projection — needs at least 7 days of data"
          }
          loading={timeSeries.isLoading}
          empty={!forecast}
          emptyMessage="Select a period with at least 7 days of usage to fit a trend."
          minHeight={280}
        >
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={forecastChartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={chrome.grid} vertical={false} />
              <XAxis dataKey="date" tick={{ fill: chrome.axis, fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
              <YAxis
                tick={{ fill: chrome.axis, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => formatCost(v, currency, true)}
                width={52}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: chrome.text }}
                labelStyle={{ color: chrome.text }}
                formatter={(v: number, name: string) => [formatCost(v, currency, true), name === "projected" ? "Projected" : "Actual"]}
              />
              <Legend formatter={(v: string) => <span style={{ color: chrome.axis, fontSize: 12 }}>{v === "projected" ? "Projected (linear)" : "Actual"}</span>} />
              <Line type="monotone" dataKey="actual" name="actual" stroke={chrome.brand} strokeWidth={2.5} dot={false} animationDuration={800} />
              <Line type="monotone" dataKey="projected" name="projected" stroke={chrome.brand} strokeWidth={2} strokeDasharray="6 4" strokeOpacity={0.6} dot={false} animationDuration={800} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <Section
          title="Detected Anomalies"
          description="Days deviating >2σ from the trailing 7-day average — computed in-app"
          icon={Sparkles}
        >
          <div className="p-5 pt-0">
            {timeSeries.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }, (_, i) => <div key={i} className="h-10 skeleton rounded-lg" />)}
              </div>
            ) : anomalies.length === 0 ? (
              <p className="text-sm text-tx-muted py-6 text-center">
                No anomalous days in the selected period.
              </p>
            ) : (
              <ul className="space-y-2">
                {anomalies.map((a) => {
                  const spike = a.sigma > 0;
                  return (
                    <li
                      key={a.date}
                      className="flex items-start gap-2.5 rounded-xl border border-border-subtle bg-app-bg p-3"
                    >
                      <AlertTriangle
                        size={14}
                        className={spike ? "text-warning mt-0.5 flex-shrink-0" : "text-info mt-0.5 flex-shrink-0"}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium text-tx-primary">
                          {formatDate(a.date)} — {formatCost(a.value, currency, true)}
                        </p>
                        <p className="text-[11px] text-tx-muted mt-0.5">
                          {Number.isFinite(a.sigma) ? `${Math.abs(a.sigma).toFixed(1)}σ` : "sharp"}{" "}
                          {spike ? "above" : "below"} the trailing average of{" "}
                          {formatCost(a.expected, currency, true)}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Section>
      </div>

      {/* EP-24.1 — Usage Heatmap: hour-of-day x day-of-week, cost-weighted */}
      <Section title="Usage Heatmap" description="Spend by hour of day and day of week (UTC)" icon={Flame}>
        <div className="p-5 pt-0 overflow-x-auto">
          {heatmap.isLoading ? (
            <div className="h-48 skeleton rounded-lg" />
          ) : heatmapCells.length === 0 ? (
            <p className="text-sm text-tx-muted py-6 text-center">No usage recorded in the selected period.</p>
          ) : (
            <div className="min-w-[560px]">
              <div className="grid gap-1" style={{ gridTemplateColumns: "40px repeat(24, 1fr)" }}>
                <div />
                {Array.from({ length: 24 }, (_, h) => (
                  <div key={h} className="text-center text-[9px] text-tx-muted">
                    {h % 3 === 0 ? h : ""}
                  </div>
                ))}
                {DAY_LABELS.map((label, day) => (
                  <div key={label} className="contents">
                    <div className="text-[10px] text-tx-muted flex items-center">{label}</div>
                    {Array.from({ length: 24 }, (_, hour) => {
                      const cell = heatmapByCell.get(`${day}-${hour}`);
                      const cost = cell ? parseFloat(cell.total_cost) : 0;
                      const intensity = cost / heatmapMax;
                      return (
                        <div
                          key={hour}
                          title={`${label} ${hour}:00 — ${formatCost(cost, currency, true)}`}
                          className="aspect-square rounded-sm"
                          style={{
                            background: cost > 0 ? `rgb(var(--color-brand) / ${Math.max(0.08, intensity)})` : "rgb(var(--color-app-muted))",
                          }}
                        />
                      );
                    })}
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-tx-muted mt-3">
                Darker cells indicate higher spend. Max cell: {formatCost(heatmapMax, currency, true)}.
              </p>
            </div>
          )}
        </div>
      </Section>

      {/* EP-24.1 — Project Spend ranking */}
      <Section title="Project Spend" description={`${projectTableData.length} projects`} icon={FolderKanban}>
        <div className="overflow-x-auto">
          <table className="w-full data-table">
            <thead>
              {projectTable.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => (
                    <th key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {projects.isLoading ? (
                Array.from({ length: 4 }, (_, i) => (
                  <tr key={i}>
                    {projectColumns.map((_, j) => (
                      <td key={j}><div className="h-4 skeleton rounded" /></td>
                    ))}
                  </tr>
                ))
              ) : projectTableData.length === 0 ? (
                <tr>
                  <td colSpan={projectColumns.length} className="text-center text-sm text-tx-muted py-6">
                    No projects with spend in the selected period.
                  </td>
                </tr>
              ) : (
                projectTable.getRowModel().rows.map((row) => (
                  <tr key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>

      {/* Data Table */}
      <Section
        title="Model Breakdown"
        description={`${tableData.length} models`}
        actions={
          <>
            <div className="flex items-center gap-2 w-full sm:flex-1 sm:w-auto sm:max-w-sm">
              <div className="relative flex-1 min-w-0">
                <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-tx-muted" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search models…"
                  className="w-full bg-app-bg border border-border-subtle rounded-lg pl-8 pr-3 py-1.5 text-xs text-tx-primary placeholder:text-tx-muted focus:border-brand focus:outline-none transition-colors"
                />
              </div>
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value as ExportFormat)}
                aria-label="Export format"
                className="bg-app-bg border border-border-subtle rounded-lg px-2 py-1.5 text-xs text-tx-secondary focus:outline-none flex-shrink-0"
              >
                <option value="models">Models</option>
                <option value="spend">Spend</option>
                <option value="providers">Providers</option>
                <option value="projects">Projects</option>
              </select>
              <button onClick={exportCSV} className="btn-outline h-8 text-xs px-3 flex-shrink-0">
                <Download size={13} />
                CSV
              </button>
            </div>
            <select
              value={pagination.pageSize}
              onChange={(e) => setPagination((p) => ({ ...p, pageIndex: 0, pageSize: Number(e.target.value) }))}
              className="bg-app-bg border border-border-subtle rounded-lg px-2 py-1.5 text-xs text-tx-secondary focus:outline-none self-start sm:self-auto"
            >
              {[10, 25, 50].map((n) => <option key={n} value={n}>{n} rows</option>)}
            </select>
          </>
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full data-table">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => (
                    <th
                      key={header.id}
                      onClick={header.column.getToggleSortingHandler()}
                      onKeyDown={(e) => {
                        if ((e.key === "Enter" || e.key === " ") && header.column.getCanSort()) {
                          e.preventDefault();
                          header.column.getToggleSortingHandler()?.(e);
                        }
                      }}
                      tabIndex={header.column.getCanSort() ? 0 : undefined}
                      aria-sort={
                        !header.column.getCanSort() ? undefined :
                        header.column.getIsSorted() === "asc" ? "ascending" :
                        header.column.getIsSorted() === "desc" ? "descending" : "none"
                      }
                      className={header.column.getCanSort() ? "cursor-pointer select-none" : ""}
                    >
                      <span className="flex items-center gap-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() && (
                          header.column.getIsSorted() === "asc" ? <ArrowUp size={10} className="text-brand" /> :
                          header.column.getIsSorted() === "desc" ? <ArrowDown size={10} className="text-brand" /> :
                          <ArrowUpDown size={10} className="opacity-40" />
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {models.isLoading
                ? Array.from({ length: 8 }, (_, i) => (
                    <tr key={i}>
                      {columns.map((_, j) => (
                        <td key={j}><div className="h-4 skeleton rounded" /></td>
                      ))}
                    </tr>
                  ))
                : table.getRowModel().rows.map((row) => (
                    <tr key={row.id}>
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-border-subtle">
          <span className="text-xs text-tx-muted">
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
          </span>
          <div className="flex gap-1">
            {[
              { label: "←", name: "Previous page", fn: () => table.previousPage(), disabled: !table.getCanPreviousPage() },
              { label: "→", name: "Next page", fn: () => table.nextPage(), disabled: !table.getCanNextPage() },
            ].map((b) => (
              <button
                key={b.label}
                onClick={b.fn}
                disabled={b.disabled}
                aria-label={b.name}
                className="w-7 h-7 rounded-md text-xs font-medium border border-border-subtle text-tx-secondary hover:text-tx-primary hover:bg-app-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                {b.label}
              </button>
            ))}
          </div>
        </div>
      </Section>
    </div>
  );
}
