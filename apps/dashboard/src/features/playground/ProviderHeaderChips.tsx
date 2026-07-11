import ProviderLogo from "../../components/ProviderLogo";
import { getProviderBrand, providerPlatformInfo } from "../../lib/providerCatalog";
import { formatCost, formatLatency } from "./format";
import { formatNumber } from "../../utils";
import type { PlaygroundConnectionOption, PlaygroundExecutionRecord, PlaygroundModelInfo } from "../../services/api";

const VALIDATION_CHIP: Record<string, { label: string; className: string }> = {
  healthy: { label: "Healthy", className: "bg-success-dim text-success" },
  invalid_api_key: { label: "Invalid key", className: "bg-danger-dim text-danger" },
  unauthorized: { label: "Not authorized", className: "bg-danger-dim text-danger" },
  quota_exceeded: { label: "Quota exceeded", className: "bg-warning-dim text-warning" },
  network_failure: { label: "Network error", className: "bg-warning-dim text-warning" },
  timeout: { label: "Timed out", className: "bg-warning-dim text-warning" },
  provider_unavailable: { label: "Unavailable", className: "bg-danger-dim text-danger" },
};

/** EP-25.4.3 Part 3 — a compact identity strip above every assistant
 * response: provider, model, connection health, latency, cost, context
 * window, capabilities — every value real (execution record, live model
 * catalog, or the connection's own last_validation_status), nothing
 * inferred or guessed. */
export default function ProviderHeaderChips({
  execution,
  connection,
  model,
}: {
  execution: PlaygroundExecutionRecord;
  connection: PlaygroundConnectionOption | undefined;
  model: PlaygroundModelInfo | undefined;
}) {
  const brand = getProviderBrand(execution.provider);
  const platform = providerPlatformInfo(execution.provider);
  const validation = connection?.last_validation_status
    ? (VALIDATION_CHIP[connection.last_validation_status] ?? { label: connection.last_validation_status, className: "bg-app-muted text-tx-muted" })
    : null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-2">
      <ProviderLogo providerId={execution.provider} size="xs" bare />
      <span className="text-xs font-semibold text-tx-primary">{brand.displayName}</span>
      <span className="text-xs text-tx-muted font-mono">{execution.model}</span>
      {platform && <span className="badge bg-app-muted text-tx-muted text-[9px]">{platform.platform}</span>}
      {validation && <span className={`badge text-[9px] ${validation.className}`}>{validation.label}</span>}
      <span className="badge bg-app-muted text-tx-muted text-[9px] font-mono">{formatLatency(execution.latency_ms)}</span>
      <span className="badge bg-app-muted text-tx-muted text-[9px] font-mono">{formatCost(execution.estimated_cost, execution.currency)}</span>
      {model?.context_window && (
        <span className="badge bg-app-muted text-tx-muted text-[9px] font-mono">{formatNumber(model.context_window)} ctx</span>
      )}
      {(model?.capabilities ?? []).slice(0, 3).map((cap) => (
        <span key={cap} className="badge bg-brand-subtle text-brand text-[9px]">
          {cap}
        </span>
      ))}
    </div>
  );
}
