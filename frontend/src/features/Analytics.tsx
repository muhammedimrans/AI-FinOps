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
} from "@tanstack/react-table";
import { motion } from "framer-motion";
import { Search, ArrowUpDown, ArrowUp, ArrowDown, Filter, Download } from "lucide-react";
import ChartCard from "../components/ChartCard";
import ProviderBadge, { PROVIDER_COLORS } from "../components/ProviderBadge";
import { useTimeSeries, useModels } from "../hooks/useDashboard";
import { formatCost, formatDate, formatNumber, formatTokens, modelDisplayName } from "../lib/utils";
import { useUIStore } from "../stores/ui";
import type { Granularity, ModelSummary } from "../types/api";

const TOOLTIP_STYLE = {
  backgroundColor: "#12121A",
  border: "1px solid #1E293B",
  borderRadius: 8,
  color: "#F8FAFC",
  fontSize: 12,
};

const PROVIDERS = ["openai", "anthropic", "google", "azure"];

const columnHelper = createColumnHelper<ModelSummary & { rank: number }>();

export default function Analytics() {
  const { currency } = useUIStore();
  const [granularity, setGranularity] = useState<Granularity>("daily");
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([{ id: "total_cost", desc: true }]);
  const [pageSize, setPageSize] = useState(25);

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
    state: { sorting, globalFilter: search, pagination: { pageIndex: 0, pageSize } },
    onSortingChange: setSorting,
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
    const rows = tableData.map((m) =>
      [m.provider, m.model_id, m.request_count, m.input_tokens, m.output_tokens, m.total_cost].join(","),
    );
    const csv = ["Provider,Model,Requests,Input Tokens,Output Tokens,Total Cost", ...rows].join("\n");
    const a = document.createElement("a");
    a.href = `data:text/csv;charset=utf-8,${encodeURIComponent(csv)}`;
    a.download = "ai-finops-analytics.csv";
    a.click();
  }

  return (
    <div className="p-6 space-y-6">
      {/* Summary stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Total Spend", value: formatCost(totalCost, currency, true), sub: "all providers" },
          { label: "Avg Cost/Request", value: formatCost(avgCost, currency), sub: "across models" },
          { label: "Min Cost/Request", value: formatCost(minCost, currency), sub: "cheapest model" },
          { label: "Max Cost/Request", value: formatCost(maxCost, currency), sub: "premium model" },
        ].map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="glass-card border border-border-subtle p-5"
          >
            <p className="text-xs text-tx-muted mb-1">{s.label}</p>
            <p className="text-xl font-bold text-tx-primary">{models.isLoading ? "—" : s.value}</p>
            <p className="text-xs text-tx-muted mt-1">{s.sub}</p>
          </motion.div>
        ))}
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
                onClick={() => setGranularity(g)}
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
            <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" vertical={false} />
            <XAxis dataKey="date" tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
            <YAxis tick={{ fill: "#475569", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatCost(v, currency, true)} width={56} />
            <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v: number) => formatCost(v, currency, true)} />
            <Legend formatter={(v) => <span style={{ color: "#94A3B8", fontSize: 12, textTransform: "capitalize" }}>{v}</span>} />
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
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass-card border border-border-subtle">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle gap-3">
          <div>
            <h3 className="text-sm font-semibold text-tx-primary">Model Breakdown</h3>
            <p className="text-xs text-tx-muted mt-0.5">{tableData.length} models</p>
          </div>
          <div className="flex items-center gap-2 flex-1 max-w-sm">
            <div className="relative flex-1">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-tx-muted" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search models…"
                className="w-full bg-app-bg border border-border-subtle rounded-lg pl-8 pr-3 py-1.5 text-xs text-tx-primary placeholder:text-tx-muted focus:border-primary focus:outline-none transition-colors"
              />
            </div>
            <button onClick={exportCSV} className="btn-outline h-8 text-xs px-3">
              <Download size={13} />
              CSV
            </button>
          </div>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="bg-app-bg border border-border-subtle rounded-lg px-2 py-1.5 text-xs text-tx-secondary focus:outline-none"
          >
            {[10, 25, 50].map((n) => <option key={n} value={n}>{n} rows</option>)}
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full data-table">
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((header) => (
                    <th
                      key={header.id}
                      onClick={header.column.getToggleSortingHandler()}
                      className={header.column.getCanSort() ? "cursor-pointer select-none" : ""}
                    >
                      <span className="flex items-center gap-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() && (
                          header.column.getIsSorted() === "asc" ? <ArrowUp size={10} /> :
                          header.column.getIsSorted() === "desc" ? <ArrowDown size={10} /> :
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
              { label: "←", fn: () => table.previousPage(), disabled: !table.getCanPreviousPage() },
              { label: "→", fn: () => table.nextPage(), disabled: !table.getCanNextPage() },
            ].map((b) => (
              <button
                key={b.label}
                onClick={b.fn}
                disabled={b.disabled}
                className="w-7 h-7 rounded-md text-xs font-medium border border-border-subtle text-tx-secondary hover:text-tx-primary hover:bg-app-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all"
              >
                {b.label}
              </button>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
