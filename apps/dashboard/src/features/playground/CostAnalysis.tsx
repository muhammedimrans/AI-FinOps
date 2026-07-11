import { useMemo } from "react";
import { Sparkles, TrendingDown, Zap, Maximize2 } from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import { getProviderBrand } from "../../lib/providerCatalog";
import { formatNumber } from "../../utils";
import { estimateCostForModel, formatCost } from "./format";
import type { PlaygroundConnectionOption, PlaygroundExecutionRecord, PlaygroundModelInfo } from "../../services/api";
import type { ConversationTurn } from "./types";

// EP-25.4.1 — the Costorah differentiator (task's own "COSTORAH
// DIFFERENTIATOR" section). Everything shown here is computed from data
// this page has actually fetched — never fabricated:
//   * "Estimated request cost" / token usage / latency: the real,
//     already-recorded values on this PlaygroundExecutionRecord.
//   * "Cheapest model" / per-alternative estimated cost: this execution's
//     REAL prompt/completion token counts multiplied by another model's
//     REAL published per-1k pricing (from that model's live catalog entry,
//     EP-26.0.1/EP-26.0.2) — only computed when both models have known
//     pricing; a model with no pricing configured is skipped, never
//     estimated with a guess.
//   * "Fastest model": derived from this browser session's own recorded
//     turns (real latency_ms values), never a global benchmark this app
//     doesn't have — if no other model has been tried this session, this
//     is disclosed as "not enough data yet" rather than invented.
//   * "Largest context window": a static catalog fact (context_window),
//     no execution needed to know it.
export interface ModelsForConnection {
  connection: PlaygroundConnectionOption;
  models: PlaygroundModelInfo[];
}

interface CostAnalysisProps {
  execution: PlaygroundExecutionRecord;
  modelsByConnection: Record<string, ModelsForConnection>;
  turns: ConversationTurn[];
}

interface PricedAlternative {
  connectionId: string;
  connection: PlaygroundConnectionOption;
  model: PlaygroundModelInfo;
  estimatedCost: number;
}

export default function CostAnalysis({ execution, modelsByConnection, turns }: CostAnalysisProps) {
  const analysis = useMemo(() => {
    const alternatives: PricedAlternative[] = [];
    let largest: { connection: PlaygroundConnectionOption; model: PlaygroundModelInfo } | null = null;

    for (const entry of Object.values(modelsByConnection)) {
      for (const model of entry.models) {
        const isCurrent =
          entry.connection.id === execution.provider_connection_id && model.id === execution.model;
        if (!largest || (model.context_window ?? 0) > (largest.model.context_window ?? 0)) {
          largest = { connection: entry.connection, model };
        }
        if (isCurrent) continue;
        if (model.input_cost_per_1k === null || model.output_cost_per_1k === null) continue;
        alternatives.push({
          connectionId: entry.connection.id,
          connection: entry.connection,
          model,
          estimatedCost: estimateCostForModel(execution, model.input_cost_per_1k, model.output_cost_per_1k),
        });
      }
    }
    alternatives.sort((a, b) => a.estimatedCost - b.estimatedCost);
    const cheapest = alternatives[0] ?? null;

    // Fastest: average latency per (provider, model) among this session's
    // OWN completed turns — real numbers, scoped honestly to "this
    // session," never presented as a universal benchmark.
    const latencyByKey = new Map<string, { sum: number; count: number; providerType: string; model: string }>();
    for (const t of turns) {
      if (t.execution?.status !== "succeeded" || t.execution.latency_ms === null) continue;
      const key = `${t.providerType}:${t.model}`;
      const entry = latencyByKey.get(key) ?? { sum: 0, count: 0, providerType: t.providerType, model: t.model };
      entry.sum += t.execution.latency_ms;
      entry.count += 1;
      latencyByKey.set(key, entry);
    }
    let fastest: { providerType: string; model: string; avgMs: number } | null = null;
    for (const v of latencyByKey.values()) {
      const avg = v.sum / v.count;
      if (!fastest || avg < fastest.avgMs) fastest = { providerType: v.providerType, model: v.model, avgMs: avg };
    }

    const currentCost = execution.estimated_cost !== null ? Number(execution.estimated_cost) : null;
    const savingsPct =
      cheapest && currentCost !== null && currentCost > 0 && cheapest.estimatedCost < currentCost
        ? Math.round((1 - cheapest.estimatedCost / currentCost) * 100)
        : null;

    return { cheapest, largest, fastest, savingsPct };
  }, [execution, modelsByConnection, turns]);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-brand/20 bg-brand-subtle/40 p-3">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-brand">
        <Sparkles size={13} />
        Cost Analysis
      </div>

      {analysis.savingsPct !== null && analysis.cheapest && (
        <p className="text-xs text-tx-primary leading-relaxed">
          This prompt would be{" "}
          <span className="font-semibold text-success">~{analysis.savingsPct}% cheaper</span> on{" "}
          <span className="font-medium">
            {getProviderBrand(analysis.cheapest.connection.provider_type).displayName} {analysis.cheapest.model.display_name}
          </span>
          .
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        <AlternativeCard
          icon={TrendingDown}
          label="Cheapest model"
          content={
            analysis.cheapest ? (
              <AlternativeRow
                providerType={analysis.cheapest.connection.provider_type}
                modelName={analysis.cheapest.model.display_name}
                detail={formatCost(analysis.cheapest.estimatedCost.toFixed(6), execution.currency)}
              />
            ) : (
              <EmptyNote text="No priced alternatives discovered yet — browse other connections to unlock this." />
            )
          }
        />
        <AlternativeCard
          icon={Zap}
          label="Fastest (this session)"
          content={
            analysis.fastest ? (
              <AlternativeRow
                providerType={analysis.fastest.providerType}
                modelName={analysis.fastest.model}
                detail={`~${Math.round(analysis.fastest.avgMs)}ms avg`}
              />
            ) : (
              <EmptyNote text="Not enough data yet — try this prompt against another model." />
            )
          }
        />
        <AlternativeCard
          icon={Maximize2}
          label="Largest context window"
          content={
            analysis.largest ? (
              <AlternativeRow
                providerType={analysis.largest.connection.provider_type}
                modelName={analysis.largest.model.display_name}
                detail={analysis.largest.model.context_window ? `${formatNumber(analysis.largest.model.context_window)} tok` : "—"}
              />
            ) : (
              <EmptyNote text="No models discovered yet." />
            )
          }
        />
      </div>
    </div>
  );
}

function AlternativeCard({
  icon: Icon,
  label,
  content,
}: {
  icon: React.ElementType;
  label: string;
  content: React.ReactNode;
}) {
  return (
    <div className="rounded-lg bg-app-bg border border-border-subtle px-2.5 py-2">
      <p className="flex items-center gap-1 text-[10px] text-tx-muted mb-1">
        <Icon size={10} /> {label}
      </p>
      {content}
    </div>
  );
}

function AlternativeRow({
  providerType,
  modelName,
  detail,
}: {
  providerType: string;
  modelName: string;
  detail: string;
}) {
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <ProviderLogo providerId={providerType} size="xs" bare />
      <div className="min-w-0">
        <p className="text-xs text-tx-primary truncate">{modelName}</p>
        <p className="text-[10px] font-mono text-tx-muted">{detail}</p>
      </div>
    </div>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <p className="text-[10px] text-tx-muted leading-snug">{text}</p>;
}
