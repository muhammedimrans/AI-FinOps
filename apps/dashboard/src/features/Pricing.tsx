import { useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Calculator, Loader2, Receipt, Search } from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import ProviderBadge from "../components/ProviderBadge";
import {
  calculatePrice,
  listModelPricing,
  ApiError,
  type PriceCalculationResult,
} from "../services/api";
import { useOrgStore } from "../stores/org";
import { formatNumber, formatDate } from "../utils";
import { toast } from "../stores/toast";

/** Format a decimal-string price per token as $/1M tokens for readability. */
function perMillion(perToken: string, currency: string): string {
  const v = parseFloat(perToken) * 1_000_000;
  const symbol = currency === "EUR" ? "€" : currency === "GBP" ? "£" : "$";
  return `${symbol}${v.toFixed(2)}`;
}

export default function Pricing() {
  const { organizationId } = useOrgStore();
  const [search, setSearch] = useState("");

  const pricing = useQuery({
    queryKey: ["pricing-catalog", organizationId],
    queryFn: () => listModelPricing(organizationId!),
    enabled: !!organizationId,
    staleTime: 30 * 60 * 1000,
  });

  const records = useMemo(() => {
    const items = pricing.data?.items ?? [];
    const q = search.trim().toLowerCase();
    const filtered = q
      ? items.filter((r) => `${r.provider} ${r.model}`.toLowerCase().includes(q))
      : items;
    return [...filtered].sort((a, b) =>
      a.provider === b.provider ? a.model.localeCompare(b.model) : a.provider.localeCompare(b.provider),
    );
  }, [pricing.data, search]);

  // ── Calculator state ────────────────────────────────────────────────────────
  const activeRecords = useMemo(
    () => (pricing.data?.items ?? []).filter((r) => r.is_active),
    [pricing.data],
  );
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [promptTokens, setPromptTokens] = useState("100000");
  const [completionTokens, setCompletionTokens] = useState("20000");
  const [result, setResult] = useState<PriceCalculationResult | null>(null);

  const selected =
    activeRecords.find((r) => `${r.provider}/${r.model}` === selectedKey) ?? activeRecords[0];

  const calc = useMutation({
    mutationFn: () =>
      calculatePrice({
        provider: selected!.provider,
        model: selected!.model,
        prompt_tokens: Math.max(0, parseInt(promptTokens, 10) || 0),
        completion_tokens: Math.max(0, parseInt(completionTokens, 10) || 0),
      }),
    onSuccess: setResult,
    onError: (err: unknown) => {
      setResult(null);
      if (err instanceof ApiError && err.status === 404) {
        toast.warning("No pricing found", "No active pricing configuration covers that model today.");
      } else {
        toast.error("Calculation failed", "Unexpected error while calculating the cost.");
      }
    },
  });

  return (
    <div className="p-4 sm:p-6 flex flex-col gap-4 sm:gap-6">
      <PageHeader
        title="Pricing"
        description="The platform's versioned pricing catalog, and a calculator backed by the same engine that prices real usage."
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        {/* Catalog */}
        <Section
          title="Pricing Catalog"
          description={`${records.length} pricing records`}
          icon={Receipt}
          actions={
            <div className="relative w-full sm:w-56">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-tx-muted" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search provider or model…"
                className="w-full bg-app-bg border border-border-subtle rounded-lg pl-8 pr-3 py-1.5 text-xs text-tx-primary placeholder:text-tx-muted focus:border-brand focus:outline-none transition-colors"
              />
            </div>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full data-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Model</th>
                  <th className="text-right">Input /1M</th>
                  <th className="text-right">Output /1M</th>
                  <th>Effective</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {pricing.isLoading
                  ? Array.from({ length: 8 }, (_, i) => (
                      <tr key={i}>
                        {Array.from({ length: 6 }, (_, j) => (
                          <td key={j}><div className="h-4 skeleton rounded" /></td>
                        ))}
                      </tr>
                    ))
                  : records.length === 0
                    ? (
                      <tr>
                        <td colSpan={6}>
                          <EmptyState
                            icon={Receipt}
                            title="No pricing records"
                            description="No pricing configurations match. Records are managed by platform administrators."
                          />
                        </td>
                      </tr>
                    )
                    : records.map((r) => (
                        <tr key={r.id} className={r.is_active ? "" : "opacity-50"}>
                          <td><ProviderBadge provider={r.provider} size="sm" /></td>
                          <td className="font-mono text-xs text-tx-primary">{r.model}</td>
                          <td className="text-right font-mono text-xs">{perMillion(r.prompt_token_price, r.currency)}</td>
                          <td className="text-right font-mono text-xs">{perMillion(r.completion_token_price, r.currency)}</td>
                          <td className="text-xs text-tx-muted whitespace-nowrap">
                            {formatDate(r.effective_from)}
                            {r.effective_to ? ` – ${formatDate(r.effective_to)}` : " →"}
                          </td>
                          <td>
                            <span className={r.is_active
                              ? "badge bg-success-dim text-success text-[10px]"
                              : "badge bg-app-muted text-tx-muted text-[10px]"}>
                              {r.is_active ? "Active" : "Inactive"}
                            </span>
                          </td>
                        </tr>
                      ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* Calculator */}
        <Section
          title="Cost Calculator"
          description="Priced by the backend engine — identical math to real usage."
          icon={Calculator}
        >
          <div className="p-5 pt-0 flex flex-col gap-4">
            <div>
              <label htmlFor="calc-model" className="text-xs text-tx-muted block mb-1.5">Model</label>
              <select
                id="calc-model"
                value={selected ? `${selected.provider}/${selected.model}` : ""}
                onChange={(e) => { setSelectedKey(e.target.value); setResult(null); }}
                disabled={activeRecords.length === 0}
                className="w-full bg-app-bg border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-primary focus:outline-none focus:border-brand disabled:opacity-50"
              >
                {activeRecords.map((r) => (
                  <option key={r.id} value={`${r.provider}/${r.model}`}>
                    {r.provider} · {r.model}
                  </option>
                ))}
                {activeRecords.length === 0 && <option>No active pricing records</option>}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="calc-in" className="text-xs text-tx-muted block mb-1.5">Input tokens</label>
                <input
                  id="calc-in"
                  type="number"
                  min={0}
                  value={promptTokens}
                  onChange={(e) => { setPromptTokens(e.target.value); setResult(null); }}
                  className="w-full bg-app-bg border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-primary font-mono focus:outline-none focus:border-brand"
                />
              </div>
              <div>
                <label htmlFor="calc-out" className="text-xs text-tx-muted block mb-1.5">Output tokens</label>
                <input
                  id="calc-out"
                  type="number"
                  min={0}
                  value={completionTokens}
                  onChange={(e) => { setCompletionTokens(e.target.value); setResult(null); }}
                  className="w-full bg-app-bg border border-border-subtle rounded-lg px-3 py-2 text-sm text-tx-primary font-mono focus:outline-none focus:border-brand"
                />
              </div>
            </div>

            <button
              onClick={() => calc.mutate()}
              disabled={!selected || calc.isPending}
              className="btn-primary w-full h-10 text-sm"
            >
              {calc.isPending ? <Loader2 size={14} className="animate-spin" /> : <Calculator size={14} />}
              Calculate cost
            </button>

            {result && (
              <div className="rounded-xl border border-brand/25 bg-brand-subtle p-4 flex flex-col gap-2" role="status">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-tx-muted">Total cost</span>
                  <span className="font-display text-xl font-bold text-tx-primary tabular-nums">
                    ${parseFloat(result.total_cost).toFixed(6)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs text-tx-secondary">
                  <span>Input ({formatNumber(result.prompt_tokens, true)} tok)</span>
                  <span className="font-mono">${parseFloat(result.prompt_cost).toFixed(6)}</span>
                </div>
                <div className="flex items-center justify-between text-xs text-tx-secondary">
                  <span>Output ({formatNumber(result.completion_tokens, true)} tok)</span>
                  <span className="font-mono">${parseFloat(result.completion_cost).toFixed(6)}</span>
                </div>
                <p className="text-[10px] text-tx-muted pt-1 border-t border-border-subtle">
                  Priced {formatDate(result.pricing_date)} · {result.currency} · versioned engine
                </p>
              </div>
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}
