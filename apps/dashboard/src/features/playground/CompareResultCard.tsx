import { Copy, Crown, Maximize2 } from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import { getProviderBrand } from "../../lib/providerCatalog";
import { renderMarkdown } from "./markdown";
import { formatCost, formatLatency } from "./format";
import { formatNumber } from "../../utils";
import { cn } from "../../utils";
import type { PlaygroundExecutionRecord, PlaygroundModelInfo } from "../../services/api";

interface CompareResultCardProps {
  result: PlaygroundExecutionRecord;
  model: PlaygroundModelInfo | undefined;
  onCopy: (text: string) => void;
  isFastest: boolean;
  isCheapest: boolean;
  isLargestContext: boolean;
}

// EP-25.4.3 Part 11 — winner badges (Fastest/Cheapest/Largest Context) are
// all objectively measurable from real data (latency_ms, estimated_cost,
// context_window). "Most Accurate" is deliberately NOT implemented —
// Costorah has no ground-truth answer to grade a response against, and the
// task's own instruction ("only when measurable") means fabricating a
// quality judgment here would be exactly the kind of invented data this
// codebase's standing convention forbids. "Strengths"/"Weaknesses" are
// likewise built only from real, derivable facts (real capability tags,
// real pricing/context presence) — never a subjective quality claim no
// evaluation actually produced.
function deriveStrengths(model: PlaygroundModelInfo | undefined, brand: { capabilities: string[] }): string[] {
  const strengths: string[] = [];
  if (model?.context_window && model.context_window >= 200_000) strengths.push("Large context window");
  if (model?.input_cost_per_1k !== undefined && model?.input_cost_per_1k !== null && model.input_cost_per_1k < 0.001) {
    strengths.push("Low input cost");
  }
  for (const cap of brand.capabilities) strengths.push(cap);
  return strengths.slice(0, 4);
}

function deriveWeaknesses(model: PlaygroundModelInfo | undefined): string[] {
  const weaknesses: string[] = [];
  if (!model) return weaknesses;
  if (model.is_deprecated) weaknesses.push("Deprecated by provider");
  if (model.input_cost_per_1k === null || model.output_cost_per_1k === null) weaknesses.push("No pricing configured");
  if (!model.context_window) weaknesses.push("Context window not reported");
  return weaknesses;
}

export default function CompareResultCard({
  result,
  model,
  onCopy,
  isFastest,
  isCheapest,
  isLargestContext,
}: CompareResultCardProps) {
  const brand = getProviderBrand(result.provider);
  const strengths = deriveStrengths(model, brand);
  const weaknesses = deriveWeaknesses(model);

  return (
    <div className="glass-card rounded-card-lg border border-border-subtle flex flex-col overflow-hidden">
      <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-border-subtle">
        <div className="flex items-center gap-2 min-w-0">
          <ProviderLogo providerId={result.provider} size="sm" />
          <div className="min-w-0">
            <p className="text-xs font-semibold text-tx-primary truncate">{brand.displayName}</p>
            <p className="text-[10px] font-mono text-tx-muted truncate">{result.model}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1 flex-shrink-0">
          {isFastest && (
            <span className="badge bg-info-dim text-info text-[9px]" title="Fastest response in this comparison">
              <Crown size={9} /> Fastest
            </span>
          )}
          {isCheapest && (
            <span className="badge bg-success-dim text-success text-[9px]" title="Cheapest response in this comparison">
              <Crown size={9} /> Cheapest
            </span>
          )}
          {isLargestContext && (
            <span className="badge bg-brand-subtle text-brand text-[9px]" title="Largest context window in this comparison">
              <Maximize2 size={9} /> Largest context
            </span>
          )}
        </div>
      </div>

      <div className="p-3.5 flex-1 min-h-[100px] max-h-[280px] overflow-y-auto text-sm text-tx-primary">
        {result.status === "failed" ? (
          <p className="text-xs text-danger">{result.error_message}</p>
        ) : (
          <div className="[&_pre]:my-0">{renderMarkdown(result.response_text ?? "")}</div>
        )}
      </div>

      {(strengths.length > 0 || weaknesses.length > 0) && (
        <div className="px-3.5 py-2 border-t border-border-subtle flex flex-col gap-1">
          {strengths.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {strengths.map((s) => (
                <span key={s} className="badge bg-success-dim text-success text-[9px]">
                  {s}
                </span>
              ))}
            </div>
          )}
          {weaknesses.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {weaknesses.map((w) => (
                <span key={w} className="badge bg-warning-dim text-warning text-[9px]">
                  {w}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-2 px-3.5 py-2 border-t border-border-subtle bg-app-muted/50">
        <div className="flex items-center gap-3 text-[10px] font-mono text-tx-muted">
          <span>{formatNumber(result.total_tokens)} tok</span>
          <span>{formatLatency(result.latency_ms)}</span>
          <span className={cn(result.estimated_cost === null && "opacity-50")}>
            {formatCost(result.estimated_cost, result.currency)}
          </span>
        </div>
        {result.response_text && (
          <button
            type="button"
            onClick={() => onCopy(result.response_text!)}
            className="p-1 text-tx-muted hover:text-tx-primary"
            aria-label={`Copy ${brand.displayName} response`}
          >
            <Copy size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
