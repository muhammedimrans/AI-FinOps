import ProviderLogo from "../../components/ProviderLogo";
import { getProviderBrand, providerPlatformInfo } from "../../lib/providerCatalog";
import { formatNumber } from "../../utils";
import type { PlaygroundConnectionOption, PlaygroundModelInfo } from "../../services/api";

// EP-25.4.1 redesign goal #8 — every field here is sourced from data this
// page (or the shared Provider Brand Registry, EP-26.0.4) already has: the
// logo/platform/service/capability-tag list come from the static, disclosed
// Provider Brand Registry (never a live capability probe); connection
// health and last-validation come straight off the PlaygroundConnectionOption
// the org's own /playground/connections endpoint already returns; context
// window comes from the selected model's own live catalog entry
// (EP-26.0.1/EP-26.0.2's real GET .../models call). Nothing here is
// fabricated or estimated.

const VALIDATION_LABELS: Record<string, { label: string; className: string }> = {
  healthy: { label: "Healthy", className: "bg-success-dim text-success" },
  invalid_api_key: { label: "Invalid API key", className: "bg-danger-dim text-danger" },
  unauthorized: { label: "Not authorized", className: "bg-danger-dim text-danger" },
  quota_exceeded: { label: "Quota exceeded", className: "bg-warning-dim text-warning" },
  network_failure: { label: "Network error", className: "bg-warning-dim text-warning" },
  timeout: { label: "Timed out", className: "bg-warning-dim text-warning" },
  provider_unavailable: { label: "Unavailable", className: "bg-danger-dim text-danger" },
};

export default function ProviderInfoCard({
  connection,
  model,
}: {
  connection: PlaygroundConnectionOption | undefined;
  model: PlaygroundModelInfo | undefined;
}) {
  if (!connection) return null;
  const brand = getProviderBrand(connection.provider_type);
  const platform = providerPlatformInfo(connection.provider_type);
  const validation = connection.last_validation_status
    ? (VALIDATION_LABELS[connection.last_validation_status] ?? { label: connection.last_validation_status, className: "bg-app-muted text-tx-muted" })
    : { label: "Not tested", className: "bg-app-muted text-tx-muted" };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <ProviderLogo providerId={connection.provider_type} size="lg" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-tx-primary truncate">{connection.display_name}</p>
          <p className="text-[11px] text-tx-muted truncate">
            {platform ? `${platform.platform} · ${platform.service}` : brand.service ?? brand.displayName}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg bg-app-muted px-2.5 py-2">
          <p className="text-[10px] text-tx-muted mb-0.5">Connection health</p>
          <span className={`badge text-[10px] ${validation.className}`}>{validation.label}</span>
        </div>
        <div className="rounded-lg bg-app-muted px-2.5 py-2">
          <p className="text-[10px] text-tx-muted mb-0.5">Context window</p>
          <p className="font-mono text-tx-primary">
            {model?.context_window ? `${formatNumber(model.context_window)} tok` : "—"}
          </p>
        </div>
      </div>

      {brand.capabilities.length > 0 && (
        <div>
          <p className="text-[10px] text-tx-muted mb-1">Capabilities</p>
          <div className="flex flex-wrap gap-1">
            {brand.capabilities.map((cap) => (
              <span key={cap} className="badge bg-app-muted text-tx-secondary text-[10px]">
                {cap}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
