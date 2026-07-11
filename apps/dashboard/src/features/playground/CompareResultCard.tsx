import { Copy, Crown } from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import { getProviderBrand } from "../../lib/providerCatalog";
import { renderMarkdown } from "./markdown";
import { formatCost, formatLatency } from "./format";
import { formatNumber } from "../../utils";
import { cn } from "../../utils";
import type { PlaygroundExecutionRecord } from "../../services/api";

interface CompareResultCardProps {
  result: PlaygroundExecutionRecord;
  onCopy: (text: string) => void;
  isFastest: boolean;
  isCheapest: boolean;
}

/** Redesign goal #9 — side-by-side response cards instead of a plain
 * table. Each card is self-contained (provider identity, response,
 * tokens/cost/latency) so a comparison across up to 8 providers reads as a
 * real comparison, not a spreadsheet row. */
export default function CompareResultCard({ result, onCopy, isFastest, isCheapest }: CompareResultCardProps) {
  const brand = getProviderBrand(result.provider);
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
        <div className="flex items-center gap-1 flex-shrink-0">
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
        </div>
      </div>

      <div className="p-3.5 flex-1 min-h-[100px] max-h-[280px] overflow-y-auto text-sm text-tx-primary">
        {result.status === "failed" ? (
          <p className="text-xs text-danger">{result.error_message}</p>
        ) : (
          <div className="[&_pre]:my-0">{renderMarkdown(result.response_text ?? "")}</div>
        )}
      </div>

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
