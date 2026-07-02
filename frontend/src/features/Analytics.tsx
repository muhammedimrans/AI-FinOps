import { useState, useMemo } from "react";
import {
  AreaChart,
  Area,
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
import { Search, ArrowUpDown, ArrowUp, ArrowDown, Download, DollarSign, Gauge, TrendingDown, TrendingUp } from "lucide-react";
import ChartCard from "../components/ChartCard";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import MetricCard from "../components/MetricCard";
import ProviderBadge, { PROVIDER_COLORS } from "../components/ProviderBadge";
import { useTimeSeries, useModels } from "../hooks/useDashboard";
import { formatCost, formatDate, formatNumber, formatTokens, modelDisplayName } from "../utils";
import { useUIStore } from "../stores/ui";
import { useChartChrome } from "../lib/chartPalette";
import { toast } from "../stores/toast";
import type { Granularity, ModelSummary } from "../types/api";

const PROVIDERS = ["openai", "anthropic", "google", "azure"];

const columnHelper = createColumnHelper<ModelSummary & { rank: number }>();

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

  const timeSeries = useTimeSeries();
  const models = useModels();

  const chartData = (timeSeries.data?.data ?? []).map((d) => ({
    date: formatDate(d.date),
    ...Object.fromEntries(
      PROVIDERS.map((p) => [p, parseFloat(d.provider_breakdown[p] ?? "0")]),
    ),
    total: parseFloat(d.total_cost),
  }));

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
        cell: (info) => <ProviderBadge provider={info.getValue()} size="sm" />,
      }),
      columnHelper.accessor("model_id", {
        header: "Model",
        cell: (info) => (
          <span className="font-mono text-xs text-tx-primary">{modelDisplayName(info.getValue())}</span>
        ),
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

  function exportCSV() {
    if (tableData.length === 0) {
      toast.warning("Nothing to export", "There is no model data for the current period.");
      return;
    }
    const rows = tableData.map((m) =>
      [m.provider, m.model_id, m.request_count, m.input_tokens, m.output_tokens, m.total_cost].join(","),
    );
    const csv = ["Provider,Model,Requests,Input Tokens,Output Tokens,Total Cost", ...rows].join("\n");
    const a = document.createElement("a");
    a.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
    a.download = "ai-finops-analytics.csv";
    a.click();
    toast.success("Export ready", `${tableData.length} models exported to CSV.`);
  }

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader title="Cost Analytics" description="Break down spend trends and model-level cost efficiency." />

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
              {PROVIDERS.map((p) => (
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
            {PROVIDERS.map((p) => (
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
