import { useMemo, useState } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { motion } from "framer-motion";
import { Medal, Search } from "lucide-react";
import ChartCard from "../components/ChartCard";
import ProviderBadge, { PROVIDER_COLORS } from "../components/ProviderBadge";
import { useModels } from "../hooks/useDashboard";
import { formatCost, formatNumber, formatTokens, modelDisplayName } from "../lib/utils";
import { useUIStore } from "../stores/ui";
import { cn } from "../lib/utils";

const TOOLTIP_STYLE = {
  backgroundColor: "#12121A",
  border: "1px solid #1E293B",
  borderRadius: 8,
  color: "#F8FAFC",
  fontSize: 12,
};

function MedalIcon({ rank }: { rank: number }) {
  if (rank === 1) return <span className="text-[#FFD700] text-sm">🥇</span>;
  if (rank === 2) return <span className="text-[#C0C0C0] text-sm">🥈</span>;
  if (rank === 3) return <span className="text-[#CD7F32] text-sm">🥉</span>;
  return <span className="text-xs text-tx-muted w-5 text-center">{rank}</span>;
}

function EfficiencyBadge({ pctRank }: { pctRank: number }) {
  if (pctRank <= 25) return <span className="badge bg-success-dim text-success text-[10px]">Efficient</span>;
  if (pctRank <= 60) return <span className="badge bg-info-dim text-info text-[10px]">Moderate</span>;
  if (pctRank <= 85) return <span className="badge bg-warning-dim text-warning text-[10px]">Pricey</span>;
  return <span className="badge bg-danger-dim text-danger text-[10px]">Premium</span>;
}

export default function Models() {
  const { currency } = useUIStore();
  const [search, setSearch] = useState("");
  const models = useModels();

  const sorted = useMemo(
    () =>
      [...(models.data?.models ?? [])]
        .sort((a, b) => parseFloat(b.total_cost) - parseFloat(a.total_cost)),
    [models.data],
  );

  const filtered = useMemo(
    () =>
      sorted.filter(
        (m) =>
          !search ||
          m.model_id.toLowerCase().includes(search.toLowerCase()) ||
          m.provider.toLowerCase().includes(search.toLowerCase()),
      ),
    [sorted, search],
  );

  // Compute per-request cost percentile rank for efficiency badge
  const costs = sorted.map((m) => parseFloat(m.avg_cost_per_request));
  const maxCost = Math.max(...costs);
  const pctRankOf = (v: number) => maxCost > 0 ? (v / maxCost) * 100 : 0;

  // Scatter data: cost vs requests, bubble = total spend
  const scatterData = sorted.map((m) => ({
    x: m.request_count / 1000,
    y: parseFloat(m.avg_cost_per_request) * 1000,
    z: parseFloat(m.total_cost),
    name: modelDisplayName(m.model_id),
    provider: m.provider,
  }));

  interface ScatterPoint {
    x: number;
    y: number;
    z: number;
    name: string;
    provider: string;
  }

  interface ScatterTooltipProps {
    active?: boolean;
    payload?: { payload: ScatterPoint }[];
  }

  const CustomScatterTooltip = ({ active, payload }: ScatterTooltipProps) => {
    if (!active || !payload?.length) return null;
    const d = payload[0]!.payload;
    return (
      <div style={TOOLTIP_STYLE} className="p-3">
        <p className="font-medium text-tx-primary mb-1">{d.name}</p>
        <p className="text-tx-muted text-[11px]">Requests: {formatNumber(d.x * 1000)}</p>
        <p className="text-tx-muted text-[11px]">$/1K req: {formatCost(d.y, currency)}</p>
        <p className="text-tx-muted text-[11px]">Total: {formatCost(d.z, currency, true)}</p>
      </div>
    );
  };

  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      {/* Leaderboard */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass-card border border-border-subtle">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 px-5 py-4 border-b border-border-subtle">
          <div>
            <h3 className="text-sm font-semibold text-tx-primary flex items-center gap-2">
              <Medal size={14} className="text-warning" />
              Model Leaderboard
            </h3>
            <p className="text-xs text-tx-muted mt-0.5">Ranked by total spend</p>
          </div>
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-tx-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="w-full sm:w-48 bg-app-bg border border-border-subtle rounded-lg pl-8 pr-3 py-1.5 text-xs text-tx-primary placeholder:text-tx-muted focus:border-brand focus:outline-none transition-colors"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full data-table">
            <thead>
              <tr>
                <th className="w-12">Rank</th>
                <th>Model</th>
                <th>Provider</th>
                <th className="text-right">Requests</th>
                <th className="text-right">In Tokens</th>
                <th className="text-right">Out Tokens</th>
                <th className="text-right">$/1K Tokens</th>
                <th>Efficiency</th>
                <th className="text-right">Total Cost</th>
              </tr>
            </thead>
            <tbody>
              {models.isLoading
                ? Array.from({ length: 8 }, (_, i) => (
                    <tr key={i}>
                      {Array.from({ length: 9 }, (_, j) => (
                        <td key={j}><div className="h-4 skeleton rounded" /></td>
                      ))}
                    </tr>
                  ))
                : filtered.length === 0
                  ? (
                    <tr>
                      <td colSpan={9} className="py-0">
                        <div className="flex flex-col items-center justify-center py-10 text-center">
                          <p className="text-sm font-medium text-tx-primary mb-1">No models found</p>
                          <p className="text-xs text-tx-muted">Try a different search term.</p>
                        </div>
                      </td>
                    </tr>
                  )
                : filtered.map((m) => {
                    const rank = sorted.indexOf(m) + 1;
                    const pct = pctRankOf(parseFloat(m.avg_cost_per_request));
                    return (
                      <tr key={m.model_id} className={rank <= 3 ? "bg-app-hover/30" : ""}>
                        <td className="text-center"><MedalIcon rank={rank} /></td>
                        <td>
                          <span className={cn(
                            "font-mono text-xs font-medium",
                            rank === 1 ? "text-[#FFD700]" : rank === 2 ? "text-[#C0C0C0]" : rank === 3 ? "text-[#CD7F32]" : "text-tx-primary",
                          )}>
                            {modelDisplayName(m.model_id)}
                          </span>
                        </td>
                        <td><ProviderBadge provider={m.provider} size="sm" /></td>
                        <td className="text-right font-mono text-xs">{formatNumber(m.request_count, true)}</td>
                        <td className="text-right font-mono text-xs">{formatTokens(m.input_tokens)}</td>
                        <td className="text-right font-mono text-xs">{formatTokens(m.output_tokens)}</td>
                        <td className="text-right font-mono text-xs">{formatCost(m.cost_per_1k_tokens, currency)}</td>
                        <td><EfficiencyBadge pctRank={pct} /></td>
                        <td className="text-right font-bold text-xs text-tx-primary">
                          {formatCost(m.total_cost, currency, true)}
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* Performance Matrix */}
      <ChartCard
        title="Performance Matrix"
        subtitle="Cost efficiency vs usage volume — bubble size = total spend"
        loading={models.isLoading}
        minHeight={320}
        legend={
          <div className="flex flex-wrap gap-3">
            {["openai", "anthropic", "google", "azure"].map((p) => (
              <div key={p} className="flex items-center gap-1.5 text-xs text-tx-muted">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: PROVIDER_COLORS[p] }} />
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </div>
            ))}
          </div>
        }
      >
        <div className="relative">
          {/* Quadrant labels */}
          <div className="absolute inset-0 pointer-events-none" style={{ padding: "8px 16px 32px 60px" }}>
            <div className="w-full h-full grid grid-cols-2 grid-rows-2">
              <div className="flex items-end justify-start pb-2 pl-2">
                <span className="text-[10px] text-success/50 font-medium">◎ High Value</span>
              </div>
              <div className="flex items-end justify-end pb-2 pr-2">
                <span className="text-[10px] text-warning/50 font-medium">Premium ◎</span>
              </div>
              <div className="flex items-start justify-start pt-2 pl-2">
                <span className="text-[10px] text-info/50 font-medium">◎ Monitor</span>
              </div>
              <div className="flex items-start justify-end pt-2 pr-2">
                <span className="text-[10px] text-danger/50 font-medium">Optimize ◎</span>
              </div>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" />
              <XAxis
                type="number"
                dataKey="x"
                name="Requests (K)"
                tick={{ fill: "#475569", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                label={{ value: "Requests (K)", position: "insideBottom", offset: -4, fill: "#475569", fontSize: 10 }}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="$/1K Req"
                tick={{ fill: "#475569", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => `$${v.toFixed(2)}`}
                width={52}
              />
              <ZAxis type="number" dataKey="z" range={[40, 800]} name="Total Spend ($)" />
              <Tooltip content={<CustomScatterTooltip />} />
              <Scatter data={scatterData} fillOpacity={0.8}>
                {scatterData.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={PROVIDER_COLORS[entry.provider] ?? "#4F46E5"}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    </div>
  );
}
