import { useMemo } from "react";
import { BarChart3 } from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import { getProviderBrand } from "../../lib/providerCatalog";
import { formatNumber } from "../../utils";
import { formatCost, formatLatency } from "./format";
import type { ConversationTurn } from "./types";

// EP-25.4.3 Part 13 — every number here is computed from this browser
// session's own completed turns (real PlaygroundExecutionRecord data) —
// never a server-side aggregate, never fabricated. Explicitly scoped and
// labeled "Current Session" (not "All time" or "This organization") since
// that's genuinely what it is: closing the tab loses this view, though the
// underlying executions remain real, persisted rows visible in History/
// Analytics regardless.
export default function SessionAnalyticsSidebar({ turns }: { turns: ConversationTurn[] }) {
  const stats = useMemo(() => {
    const succeeded = turns.filter((t) => t.execution?.status === "succeeded");
    const requests = succeeded.length;
    const tokens = succeeded.reduce((sum, t) => sum + (t.execution?.total_tokens ?? 0), 0);
    const cost = succeeded.reduce((sum, t) => sum + Number(t.execution?.estimated_cost ?? 0), 0);
    const latencies = succeeded.map((t) => t.execution?.latency_ms ?? 0).filter((n) => n > 0);
    const avgLatency = latencies.length ? latencies.reduce((a, b) => a + b, 0) / latencies.length : null;

    const modelCounts = new Map<string, number>();
    const providerCounts = new Map<string, number>();
    for (const t of succeeded) {
      modelCounts.set(t.model, (modelCounts.get(t.model) ?? 0) + 1);
      providerCounts.set(t.providerType, (providerCounts.get(t.providerType) ?? 0) + 1);
    }
    const mostUsedModel = [...modelCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    const mostUsedProvider = [...providerCounts.entries()].sort((a, b) => b[1] - a[1])[0];

    return { requests, tokens, cost, avgLatency, mostUsedModel, mostUsedProvider };
  }, [turns]);

  return (
    <div className="glass-card rounded-card-lg border border-border-subtle p-4">
      <div className="flex items-center gap-1.5 mb-3">
        <BarChart3 size={13} className="text-tx-muted" />
        <h3 className="text-xs font-semibold text-tx-primary">Current session</h3>
      </div>
      <div className="grid grid-cols-2 gap-2 mb-3">
        <Stat label="Requests" value={formatNumber(stats.requests)} />
        <Stat label="Tokens" value={formatNumber(stats.tokens)} />
        <Stat label="Cost" value={stats.cost > 0 ? formatCost(stats.cost.toFixed(6), "USD") : "—"} />
        <Stat label="Avg latency" value={stats.avgLatency !== null ? formatLatency(stats.avgLatency) : "—"} />
      </div>
      <div className="flex flex-col gap-2">
        <div>
          <p className="text-[10px] text-tx-muted mb-1">Most used model</p>
          {stats.mostUsedModel ? (
            <p className="text-xs font-mono text-tx-primary">
              {stats.mostUsedModel[0]} <span className="text-tx-muted">×{stats.mostUsedModel[1]}</span>
            </p>
          ) : (
            <p className="text-xs text-tx-muted">—</p>
          )}
        </div>
        <div>
          <p className="text-[10px] text-tx-muted mb-1">Most used provider</p>
          {stats.mostUsedProvider ? (
            <div className="flex items-center gap-1.5">
              <ProviderLogo providerId={stats.mostUsedProvider[0]} size="xs" bare />
              <p className="text-xs text-tx-primary">
                {getProviderBrand(stats.mostUsedProvider[0]).displayName} <span className="text-tx-muted">×{stats.mostUsedProvider[1]}</span>
              </p>
            </div>
          ) : (
            <p className="text-xs text-tx-muted">—</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-app-muted px-2.5 py-2">
      <p className="text-[10px] text-tx-muted">{label}</p>
      <p className="text-sm font-mono text-tx-primary">{value}</p>
    </div>
  );
}
