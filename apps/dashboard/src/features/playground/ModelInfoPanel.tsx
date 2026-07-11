import { Check, ExternalLink, Minus } from "lucide-react";
import { getProviderBrand } from "../../lib/providerCatalog";
import { formatNumber } from "../../utils";
import type { PlaygroundModelInfo } from "../../services/api";

// EP-25.4.3 Part 10 — every field is read directly from the model's own
// live catalog entry (GET .../playground/connections/{id}/models, real
// since EP-26.0.1/EP-26.0.2) — the backend's ModelCapabilityFlag enum
// (app/providers/models.py) has exactly six values: streaming,
// tool_calling, vision, audio, function_calling, fine_tuning. There is no
// "reasoning" flag and no "knowledge cutoff" field anywhere in
// ModelMetadata — both are shown here as explicitly "not tracked" rather
// than guessed, since fabricating either would violate this codebase's
// standing no-fake-data convention.
const CAPABILITY_ROWS: { key: string; label: string }[] = [
  { key: "streaming", label: "Streaming" },
  { key: "vision", label: "Vision" },
  { key: "audio", label: "Audio" },
  { key: "function_calling", label: "Function calling" },
  { key: "tool_calling", label: "Tool calling" },
];

function CapabilityRow({ label, has }: { label: string; has: boolean }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[11px] text-tx-secondary">{label}</span>
      {has ? <Check size={13} className="text-success" /> : <Minus size={13} className="text-tx-disabled" />}
    </div>
  );
}

export default function ModelInfoPanel({ model, providerType }: { model: PlaygroundModelInfo; providerType: string }) {
  const brand = getProviderBrand(providerType);
  const caps = new Set(model.capabilities);

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-border-subtle bg-app-muted p-3">
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <p className="text-tx-muted">Context window</p>
          <p className="font-mono text-tx-primary">{model.context_window ? `${formatNumber(model.context_window)} tok` : "—"}</p>
        </div>
        <div>
          <p className="text-tx-muted">Max output tokens</p>
          <p className="font-mono text-tx-primary">{model.max_output_tokens ? formatNumber(model.max_output_tokens) : "—"}</p>
        </div>
        <div>
          <p className="text-tx-muted">Input pricing</p>
          <p className="font-mono text-tx-primary">{model.input_cost_per_1k !== null ? `$${model.input_cost_per_1k}/1K tok` : "Not priced"}</p>
        </div>
        <div>
          <p className="text-tx-muted">Output pricing</p>
          <p className="font-mono text-tx-primary">{model.output_cost_per_1k !== null ? `$${model.output_cost_per_1k}/1K tok` : "Not priced"}</p>
        </div>
      </div>

      <div className="border-t border-border-subtle pt-2">
        {CAPABILITY_ROWS.map((row) => (
          <CapabilityRow key={row.key} label={row.label} has={caps.has(row.key)} />
        ))}
        <div className="flex items-center justify-between py-1" title="Not tracked by Costorah's provider catalog — no adapter reports a reasoning-mode flag.">
          <span className="text-[11px] text-tx-muted italic">Reasoning</span>
          <span className="text-[10px] text-tx-disabled">Not tracked</span>
        </div>
        <div className="flex items-center justify-between py-1" title="Not returned by any provider's model-listing endpoint — Costorah has no source for this field.">
          <span className="text-[11px] text-tx-muted italic">Knowledge cutoff</span>
          <span className="text-[10px] text-tx-disabled">Not available</span>
        </div>
      </div>

      {model.is_deprecated && (
        <p className="text-[10px] text-warning">This model is flagged deprecated by the provider's own catalog.</p>
      )}

      <a
        href={brand.website}
        target="_blank"
        rel="noreferrer"
        className="btn-ghost h-7 px-2 text-[11px] inline-flex items-center gap-1 self-start"
      >
        <ExternalLink size={11} /> {brand.displayName} documentation
      </a>
    </div>
  );
}
