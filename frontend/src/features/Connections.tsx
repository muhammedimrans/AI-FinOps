import { useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Activity,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Loader2,
  PlugZap,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import {
  getProviderInfo,
  getProviderModels,
  testProviderConnection,
  ApiError,
  type TestConnectionResponse,
} from "../services/api";
import { PROVIDER_COLORS } from "../lib/providerCatalog";
import { cn, formatNumber, providerDisplayName } from "../utils";
import { toast } from "../stores/toast";

// Adapters the backend can actually talk to today (kept in sync with the
// backend's _PRODUCTION_PROVIDERS). Everything else 404s at the API.
const PRODUCTION_ADAPTERS = ["openai", "anthropic"];
const IN_DEVELOPMENT_ADAPTERS = ["google", "azure_openai", "grok", "openrouter", "ollama"];

const ADAPTER_LABELS: Record<string, string> = {
  azure_openai: "Azure OpenAI",
  grok: "Grok (xAI)",
  openrouter: "OpenRouter",
  ollama: "Ollama",
};

function adapterLabel(id: string): string {
  return ADAPTER_LABELS[id] ?? providerDisplayName(id);
}

const CAPABILITY_LABELS: [key: string, label: string][] = [
  ["supports_streaming", "Streaming"],
  ["supports_tool_calling", "Tool calling"],
  ["supports_vision", "Vision"],
  ["supports_usage_api", "Usage API"],
  ["supports_fine_tuning", "Fine-tuning"],
];

function TestResultBadge({ result }: { result: TestConnectionResponse }) {
  const ok = result.auth_valid && result.status.is_connected;
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-xl border p-3 text-xs",
        ok ? "bg-success-dim border-success/25" : "bg-danger-dim border-danger/25",
      )}
      role="status"
    >
      {ok ? (
        <CheckCircle2 size={14} className="text-success mt-0.5 flex-shrink-0" />
      ) : (
        <XCircle size={14} className="text-danger mt-0.5 flex-shrink-0" />
      )}
      <div className="min-w-0">
        <p className={cn("font-semibold", ok ? "text-success" : "text-danger")}>
          {ok ? "Connected — API key valid" : "Connection failed"}
        </p>
        <p className="text-tx-muted mt-0.5">
          {result.status.latency_ms != null && `${Math.round(result.status.latency_ms)}ms · `}
          health: {result.status.health_status}
          {result.status.error_message && ` · ${result.status.error_message}`}
        </p>
      </div>
    </div>
  );
}

function ProductionProviderCard({ providerId, index }: { providerId: string; index: number }) {
  const [modelsOpen, setModelsOpen] = useState(false);
  const [testResult, setTestResult] = useState<TestConnectionResponse | null>(null);

  const info = useQuery({
    queryKey: ["provider-info", providerId],
    queryFn: () => getProviderInfo(providerId),
    staleTime: 60 * 60 * 1000,
  });

  const models = useQuery({
    queryKey: ["provider-models", providerId],
    queryFn: () => getProviderModels(providerId),
    enabled: modelsOpen,
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });

  const test = useMutation({
    mutationFn: () => testProviderConnection(providerId),
    onSuccess: (result) => setTestResult(result),
    onError: (err: unknown) => {
      setTestResult(null);
      if (err instanceof ApiError && err.status === 401) {
        toast.error("Authentication failed", `${adapterLabel(providerId)} rejected the configured API key.`);
      } else if (err instanceof ApiError && err.status === 502) {
        toast.error("Provider unreachable", `${adapterLabel(providerId)} could not be reached from the server.`);
      } else {
        toast.error("Test failed", "Unexpected error while testing the connection.");
      }
    },
  });

  const color = PROVIDER_COLORS[providerId] ?? "#888";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="glass-card rounded-card-lg border border-border-subtle p-5"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
            style={{ background: color }}
          >
            {adapterLabel(providerId).slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-tx-primary truncate">
              {info.data?.display_name ?? adapterLabel(providerId)}
            </h3>
            <p className="text-xs text-tx-muted">
              {info.data ? `Auth: ${info.data.authentication_type}` : "Production adapter"}
            </p>
          </div>
        </div>
        <span className="badge bg-success-dim text-success text-[10px] flex-shrink-0">
          <ShieldCheck size={10} /> Production
        </span>
      </div>

      {/* Capabilities from the real /info endpoint */}
      {info.isLoading ? (
        <div className="h-6 skeleton rounded mb-4" />
      ) : info.data ? (
        <div className="flex flex-wrap gap-1.5 mb-4">
          {CAPABILITY_LABELS.filter(([key]) => (info.data as unknown as Record<string, boolean>)[key]).map(
            ([key, label]) => (
              <span key={key} className="badge bg-app-muted text-tx-secondary text-[10px]">{label}</span>
            ),
          )}
          {info.data.max_context_window && (
            <span className="badge bg-app-muted text-tx-secondary text-[10px]">
              {formatNumber(info.data.max_context_window, true)} ctx
            </span>
          )}
        </div>
      ) : (
        <p className="text-xs text-tx-muted mb-4">Provider metadata unavailable.</p>
      )}

      {testResult && (
        <div className="mb-4">
          <TestResultBadge result={testResult} />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => test.mutate()}
          disabled={test.isPending}
          className="btn-primary h-8 text-xs px-3"
        >
          {test.isPending ? <Loader2 size={13} className="animate-spin" /> : <Activity size={13} />}
          {test.isPending ? "Testing…" : "Test connection"}
        </button>
        <button
          onClick={() => setModelsOpen((o) => !o)}
          className="btn-outline h-8 text-xs px-3"
          aria-expanded={modelsOpen}
        >
          <ChevronDown size={13} className={cn("transition-transform duration-base", modelsOpen && "rotate-180")} />
          {modelsOpen ? "Hide models" : "Live models"}
        </button>
        {info.data?.documentation_url && (
          <a
            href={info.data.documentation_url}
            target="_blank"
            rel="noreferrer"
            className="btn-ghost h-8 text-xs px-3 inline-flex items-center gap-1.5"
          >
            <BookOpen size={13} /> Docs
          </a>
        )}
      </div>

      {/* Live model list, fetched from the provider API on demand */}
      {modelsOpen && (
        <div className="mt-4 border-t border-border-subtle pt-3">
          {models.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }, (_, i) => <div key={i} className="h-5 skeleton rounded" />)}
            </div>
          ) : models.isError ? (
            <p className="text-xs text-danger">
              Could not fetch the live model list — check that the provider API key is configured on the server.
            </p>
          ) : (
            <>
              <p className="text-[10px] text-tx-muted uppercase tracking-wide mb-2">
                {models.data?.count ?? 0} models · live from the provider API
              </p>
              <div className="overflow-x-auto max-h-64 overflow-y-auto">
                <table className="w-full data-table">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th className="text-right">Context</th>
                      <th className="text-right">In $/1K</th>
                      <th className="text-right">Out $/1K</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(models.data?.models ?? []).map((m) => (
                      <tr key={m.id} className={m.is_deprecated ? "opacity-50" : ""}>
                        <td className="font-mono text-xs text-tx-primary">
                          {m.id}
                          {m.is_deprecated && <span className="ml-1.5 badge bg-warning-dim text-warning text-[9px]">deprecated</span>}
                        </td>
                        <td className="text-right font-mono text-xs">
                          {m.context_window ? formatNumber(m.context_window, true) : "—"}
                        </td>
                        <td className="text-right font-mono text-xs">
                          {m.input_cost_per_1k != null ? `$${m.input_cost_per_1k.toFixed(4)}` : "—"}
                        </td>
                        <td className="text-right font-mono text-xs">
                          {m.output_cost_per_1k != null ? `$${m.output_cost_per_1k.toFixed(4)}` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </motion.div>
  );
}

export default function Connections() {
  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader
        title="Provider Connections"
        description="Verify credentials, inspect capabilities, and browse live model lists for each adapter."
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {PRODUCTION_ADAPTERS.map((p, i) => (
          <ProductionProviderCard key={p} providerId={p} index={i} />
        ))}
      </div>

      <Section
        title="Adapters in development"
        description="Registered in the platform but not yet promoted to production — connection testing is unavailable until each adapter ships."
        icon={Wrench}
      >
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {IN_DEVELOPMENT_ADAPTERS.map((p) => (
            <div
              key={p}
              className="rounded-xl border border-dashed border-border-subtle p-4 flex flex-col items-center text-center gap-2 opacity-70"
            >
              <div className="w-9 h-9 rounded-lg bg-app-muted flex items-center justify-center">
                <PlugZap size={15} className="text-tx-muted" />
              </div>
              <span className="text-xs font-medium text-tx-secondary">{adapterLabel(p)}</span>
              <span className="badge bg-app-muted text-tx-muted text-[9px]">In development</span>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
