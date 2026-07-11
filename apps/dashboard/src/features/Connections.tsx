import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Clock,
  Download,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Pencil,
  Plug,
  PlugZap,
  Plus,
  RefreshCw,
  RotateCw,
  ShieldCheck,
  Timer,
  Trash2,
  Wrench,
  XCircle,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import ProviderLogo from "../components/ProviderLogo";
import {
  getProviderInfo,
  getProviderModels,
  testProviderConnection,
  listProviderConnections,
  createProviderConnection,
  updateProviderConnection,
  deleteProviderConnection,
  testProviderConnectionById,
  rotateProviderConnectionKey,
  getProviderConnectionSyncStatus,
  syncProviderConnection,
  syncAllProviderConnections,
  getSchedulerStatus,
  ApiError,
  type TestConnectionResponse,
  type TestProviderConnectionResult,
  type ProviderConnectionRecord,
  type SyncStatusResponse,
} from "../services/api";
import {
  CONNECTABLE_PROVIDERS,
  connectableLabel,
  hasKnownUsageApi,
  providerPlatformInfo,
  getProviderBrand,
} from "../lib/providerCatalog";
import { cn, formatNumber, providerDisplayName } from "../utils";
import { toast } from "../stores/toast";
import { useOrgStore } from "../stores/org";

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

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="glass-card rounded-card-lg border border-border-subtle p-5"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <ProviderLogo providerId={providerId} size="lg" />
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

const HEALTH_BADGE: Record<string, { className: string; label: string }> = {
  healthy: { className: "bg-success-dim text-success", label: "Healthy" },
  critical: { className: "bg-danger-dim text-danger", label: "Critical" },
  warning: { className: "bg-warning-dim text-warning", label: "Warning" },
  recovering: { className: "bg-warning-dim text-warning", label: "Recovering" },
  unknown: { className: "bg-app-muted text-tx-muted", label: "Not tested" },
};

function HealthBadge({ status }: { status: string }) {
  const cfg = HEALTH_BADGE[status] ?? HEALTH_BADGE["unknown"]!;
  return <span className={cn("badge text-[10px]", cfg.className)}>{cfg.label}</span>;
}

// EP-22 Part 3 — normalized validation-outcome vocabulary, one label per
// ProviderValidationStatus value. Never derived from raw provider error text.
const VALIDATION_LABELS: Record<string, string> = {
  healthy: "Connection healthy",
  invalid_api_key: "Invalid API key",
  unauthorized: "Not authorized",
  quota_exceeded: "Quota exceeded",
  network_failure: "Network error",
  timeout: "Timed out",
  provider_unavailable: "Provider unavailable",
};

function formatValidatedAt(iso: string | null): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return null;
  }
}

// EP-23.3 — one badge per SyncRunStatus value.
const SYNC_STATUS_BADGE: Record<string, { className: string; label: string }> = {
  never_synced: { className: "bg-app-muted text-tx-muted", label: "Never synced" },
  pending: { className: "bg-app-muted text-tx-muted", label: "Pending" },
  running: { className: "bg-warning-dim text-warning", label: "Syncing…" },
  success: { className: "bg-success-dim text-success", label: "Synced" },
  failed: { className: "bg-danger-dim text-danger", label: "Sync failed" },
};

function formatCostImported(items: SyncStatusResponse["estimated_cost_imported"]): string | null {
  if (items.length === 0) return null;
  return items
    .map((item) => `${Number(item.total_cost).toLocaleString(undefined, { style: "currency", currency: item.currency })}`)
    .join(" + ");
}

/** EP-23.3 — per-connection sync status + Sync Now / Refresh Status controls. */
function SyncStatusPanel({
  organizationId,
  connection,
}: {
  organizationId: string;
  connection: ProviderConnectionRecord;
}) {
  const queryClient = useQueryClient();

  const status = useQuery({
    queryKey: ["provider-connection-sync-status", organizationId, connection.id],
    queryFn: () => getProviderConnectionSyncStatus(organizationId, connection.id),
  });

  const sync = useMutation({
    mutationFn: () => syncProviderConnection(organizationId, connection.id),
    onSuccess: (result) => {
      queryClient.setQueryData(
        ["provider-connection-sync-status", organizationId, connection.id],
        result.sync_status,
      );
      if (result.run.status === "completed") {
        toast.success(
          "Sync complete",
          `Imported ${formatNumber(result.run.records_imported)} record${result.run.records_imported === 1 ? "" : "s"}.`,
        );
      } else {
        toast.error("Sync failed", result.run.error_message ?? "Please try again.");
      }
    },
    onError: (err: unknown) => {
      toast.error("Couldn't sync", err instanceof ApiError ? err.message : "Please try again.");
    },
  });

  const data = status.data;
  const badge = SYNC_STATUS_BADGE[data?.sync_status ?? "never_synced"] ?? SYNC_STATUS_BADGE["never_synced"]!;
  const lastSyncLabel = formatValidatedAt(data?.last_sync_completed_at ?? null);
  const costLabel = data ? formatCostImported(data.estimated_cost_imported) : null;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border-subtle bg-app-bg p-2.5 ml-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("badge text-[10px]", badge.className)}>{badge.label}</span>
        {status.isLoading && <Loader2 size={11} className="animate-spin text-tx-muted" />}
        {lastSyncLabel && <span className="text-[11px] text-tx-muted">Last sync {lastSyncLabel}</span>}
        {data && !data.supports_usage_sync && (
          <span className="text-[11px] text-tx-muted">
            This provider has no bulk usage-history API — sync runs normally (checkpoint, retry,
            scheduler) but will import 0 records until one exists.
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => void status.refetch()}
            disabled={status.isFetching}
            className="btn-ghost h-7 px-2 text-[11px] inline-flex items-center gap-1"
          >
            <RotateCw size={11} className={status.isFetching ? "animate-spin" : undefined} />
            Refresh status
          </button>
          <button
            onClick={() => sync.mutate()}
            disabled={sync.isPending}
            className="btn-outline h-7 px-2 text-[11px] inline-flex items-center gap-1 disabled:opacity-60"
          >
            {sync.isPending ? <Loader2 size={11} className="animate-spin" /> : <Download size={11} />}
            {sync.isPending ? "Syncing…" : "Sync now"}
          </button>
        </div>
      </div>

      {data && data.sync_status !== "never_synced" && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-tx-muted">
          <span>{formatNumber(data.records_imported)} records imported</span>
          <span>{formatNumber(data.tokens_imported)} tokens imported</span>
          {costLabel && <span>{costLabel} estimated cost imported</span>}
        </div>
      )}

      {data?.last_error && <p className="text-[11px] text-danger">{data.last_error}</p>}
    </div>
  );
}

/** EP-22 Part 6 — masked-by-default API key input with a reveal toggle. */
function ApiKeyInput({
  value,
  onChange,
  disabled,
  placeholder,
  autoFocus,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  placeholder: string;
  autoFocus?: boolean;
}) {
  const [revealed, setRevealed] = useState(false);
  return (
    <div className="relative flex-1 min-w-0">
      <input
        type={revealed ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        autoFocus={autoFocus}
        autoComplete="off"
        spellCheck={false}
        className="w-full rounded-lg border border-border-subtle bg-app-bg px-3 py-2 pr-9 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60 font-mono"
      />
      <button
        type="button"
        onClick={() => setRevealed((r) => !r)}
        disabled={disabled}
        className="absolute right-2 top-1/2 -translate-y-1/2 text-tx-muted hover:text-tx-primary disabled:opacity-60"
        aria-label={revealed ? "Hide API key" : "Reveal API key"}
        tabIndex={-1}
      >
        {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
  );
}

export function AddConnectionForm({
  organizationId,
  onDone,
}: {
  organizationId: string;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [providerType, setProviderType] = useState(CONNECTABLE_PROVIDERS[0]!.value);
  const [displayName, setDisplayName] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  const requiresBaseUrl = providerType === "azure_openai";

  const create = useMutation({
    mutationFn: () =>
      createProviderConnection(organizationId, {
        provider_type: providerType,
        display_name: displayName.trim(),
        ...(apiKey.trim() && { api_key: apiKey.trim() }),
        ...(baseUrl.trim() && { base_url: baseUrl.trim() }),
      }),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["provider-connections", organizationId] });
      if (created.last_validation_status === "healthy") {
        toast.success("Connection added", `${created.display_name} is verified and ready.`);
      } else if (created.last_validation_status) {
        toast.warning(
          "Connection added — validation failed",
          created.last_error ?? "The credential could not be verified.",
        );
      } else {
        toast.success("Connection added", `${created.display_name} was saved.`);
      }
      onDone();
    },
    onError: (err: unknown) => {
      toast.error(
        "Couldn't add connection",
        err instanceof ApiError ? err.message : "Please try again.",
      );
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (displayName.trim().length === 0) return;
        if (requiresBaseUrl && baseUrl.trim().length === 0) return;
        create.mutate();
      }}
      className="flex flex-col gap-2 rounded-xl border border-border-subtle bg-app-muted p-3"
    >
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="flex items-center gap-2">
          <ProviderLogo providerId={providerType} size="sm" />
          <select
            value={providerType}
            onChange={(e) => setProviderType(e.target.value)}
            disabled={create.isPending}
            className="rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
          >
            {CONNECTABLE_PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Connection name (e.g. Production OpenAI)"
          disabled={create.isPending}
          autoFocus
          className="flex-1 min-w-0 rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
        />
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        <ApiKeyInput
          value={apiKey}
          onChange={setApiKey}
          disabled={create.isPending}
          placeholder={
            providerType === "ollama" ? "API key (not required for Ollama)" : "API key (sk-...)"
          }
        />
        <input
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder={
            requiresBaseUrl ? "Resource endpoint (required, e.g. https://my-resource.openai.azure.com)" : "Base URL (optional)"
          }
          disabled={create.isPending}
          className="flex-1 min-w-0 rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
        />
      </div>
      <p className="text-[11px] text-tx-muted">
        The key is encrypted immediately and validated live against {connectableLabel(providerType)} on save.
        It is never shown again in full.
      </p>
      <div className="flex gap-2 self-end">
        <button
          type="submit"
          disabled={
            create.isPending ||
            displayName.trim().length === 0 ||
            (requiresBaseUrl && baseUrl.trim().length === 0)
          }
          className="btn-primary h-9 px-4 text-xs disabled:opacity-60 inline-flex items-center gap-1.5"
        >
          {create.isPending && <Loader2 size={13} className="animate-spin" />}
          {create.isPending ? "Adding & validating…" : "Add"}
        </button>
        <button type="button" onClick={onDone} className="btn-ghost h-9 px-3 text-xs">
          Cancel
        </button>
      </div>
    </form>
  );
}

function ConnectionRow({
  organizationId,
  connection,
}: {
  organizationId: string;
  connection: ProviderConnectionRecord;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(connection.display_name);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [lastTestResult, setLastTestResult] = useState<TestProviderConnectionResult | null>(null);
  const brand = getProviderBrand(connection.provider_type);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["provider-connections", organizationId] });

  const rename = useMutation({
    mutationFn: () =>
      updateProviderConnection(organizationId, connection.id, { display_name: name.trim() }),
    onSuccess: () => {
      setEditing(false);
      void invalidate();
      toast.success("Connection renamed");
    },
    onError: (err: unknown) => {
      toast.error(
        "Couldn't rename connection",
        err instanceof ApiError ? err.message : "Please try again.",
      );
    },
  });

  const toggleActive = useMutation({
    mutationFn: () =>
      updateProviderConnection(organizationId, connection.id, {
        is_active: !connection.is_active,
      }),
    onSuccess: () => void invalidate(),
    onError: () => toast.error("Couldn't update connection"),
  });

  const test = useMutation({
    mutationFn: () => testProviderConnectionById(organizationId, connection.id),
    onSuccess: (result) => {
      void invalidate();
      setLastTestResult(result);
      if (result.tested) {
        toast[result.health_status === "healthy" ? "success" : "error"]("Test complete", result.detail);
      } else {
        toast.info("Not testable yet", result.detail);
      }
    },
    onError: () => {
      setLastTestResult(null);
      toast.error(
        "Test failed",
        `Couldn't reach ${brand.displayName}. Check the connection's API key and try again.`,
      );
    },
  });

  const rotate = useMutation({
    mutationFn: () => rotateProviderConnectionKey(organizationId, connection.id, newKey.trim()),
    onSuccess: (updated) => {
      void invalidate();
      setRotating(false);
      setNewKey("");
      if (updated.last_validation_status === "healthy") {
        toast.success("Key rotated", "The new key was validated successfully.");
      } else {
        toast.warning(
          "Key rotated — validation failed",
          updated.last_error ?? "The new credential could not be verified.",
        );
      }
    },
    onError: (err: unknown) => {
      toast.error(
        "Couldn't rotate key",
        err instanceof ApiError ? err.message : "Please try again.",
      );
    },
  });

  const remove = useMutation({
    mutationFn: () => deleteProviderConnection(organizationId, connection.id),
    onSuccess: () => {
      void invalidate();
      toast.success("Connection deleted");
    },
    onError: () => toast.error("Couldn't delete connection"),
  });

  const lastValidatedAt = connection.last_recovery_at ?? connection.last_failure_at;
  const lastValidatedLabel = formatValidatedAt(lastValidatedAt);

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border-subtle bg-app-muted p-3">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex items-center gap-2.5 min-w-0 flex-1">
          <ProviderLogo providerId={connection.provider_type} size="md" />
          {editing ? (
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={rename.isPending}
              autoFocus
              className="min-w-0 flex-1 rounded-lg border border-border-subtle bg-app-bg px-2 py-1 text-sm text-tx-primary outline-none focus:border-brand"
            />
          ) : (
            <div className="min-w-0">
              <p className="text-sm text-tx-primary truncate">{connection.display_name}</p>
              <p className="text-[11px] text-tx-muted">
                {connectableLabel(connection.provider_type)}
                {connection.masked_api_key && (
                  <span className="ml-1.5 font-mono text-tx-secondary">{connection.masked_api_key}</span>
                )}
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <HealthBadge status={connection.health_status} />
          <span className={cn("badge text-[10px]", connection.is_active ? "bg-success-dim text-success" : "bg-app-muted text-tx-muted")}>
            {connection.is_active ? "Active" : "Inactive"}
          </span>
          {/* EP-26.0.2 — Provider/Platform/Service identity. Purely
              display-layer (providerCatalog.ts's providerPlatformInfo);
              today this only renders for Google, whose ProviderType
              exclusively targets AI Studio / the Gemini Developer API, not
              the future, not-yet-built Vertex AI integration. */}
          {providerPlatformInfo(connection.provider_type) && (
            <span
              className="badge text-[10px] bg-app-muted text-tx-secondary"
              title="The specific Google platform and service this connection targets."
            >
              {providerPlatformInfo(connection.provider_type)!.platform} ·{" "}
              {providerPlatformInfo(connection.provider_type)!.service}
            </span>
          )}
          {/* EP-24.3 — informational capability badge, mirrors the backend's
              _KNOWN_USAGE_API_PROVIDERS list; never gates any action.
              EP-26.0.3.3 — explicit "Historical usage: Supported/
              Unavailable" wording, so a customer never has to guess what
              "Usage API" means for their own spend tracking. */}
          <span
            className={cn(
              "badge text-[10px]",
              hasKnownUsageApi(connection.provider_type)
                ? "bg-success-dim text-success"
                : "bg-app-muted text-tx-muted",
            )}
            title={
              hasKnownUsageApi(connection.provider_type)
                ? "This provider has a bulk usage-history API — background syncs import real usage records automatically."
                : "This provider has no bulk usage-history API — background syncs run normally but import 0 records. Use AI Playground to generate tracked usage instead."
            }
          >
            {hasKnownUsageApi(connection.provider_type)
              ? "Historical usage: Supported"
              : "Historical usage: Unavailable"}
          </span>

          {editing ? (
            <>
              <button
                onClick={() => rename.mutate()}
                disabled={rename.isPending || name.trim().length === 0}
                className="btn-primary h-7 px-2 text-[11px] disabled:opacity-60"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setName(connection.display_name);
                }}
                className="btn-ghost h-7 px-2 text-[11px]"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => test.mutate()}
                disabled={test.isPending}
                className="btn-outline h-7 px-2 text-[11px] inline-flex items-center gap-1"
              >
                {test.isPending ? <Loader2 size={11} className="animate-spin" /> : <Activity size={11} />}
                Test
              </button>
              <button
                onClick={() => setRotating((r) => !r)}
                className="btn-ghost h-7 px-2 text-[11px] inline-flex items-center gap-1"
                aria-expanded={rotating}
              >
                <RefreshCw size={11} /> Rotate key
              </button>
              <button
                onClick={() => toggleActive.mutate()}
                disabled={toggleActive.isPending}
                className="btn-ghost h-7 px-2 text-[11px]"
              >
                {connection.is_active ? "Deactivate" : "Activate"}
              </button>
              <button
                onClick={() => setEditing(true)}
                className="text-tx-muted hover:text-tx-primary"
                aria-label="Rename connection"
              >
                <Pencil size={13} />
              </button>
              <button
                onClick={() => setConfirmingDelete(true)}
                className="text-tx-muted hover:text-danger"
                aria-label="Delete connection"
              >
                <Trash2 size={13} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* EP-22 Part 6 — health badge, last validation timestamp, error message */}
      {(connection.last_validation_status || lastValidatedLabel) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-tx-muted pl-5">
          {connection.last_validation_status && (
            <span className={connection.last_validation_status === "healthy" ? "text-success" : "text-danger"}>
              {VALIDATION_LABELS[connection.last_validation_status] ?? connection.last_validation_status}
            </span>
          )}
          {lastValidatedLabel && <span>Last checked {lastValidatedLabel}</span>}
          {connection.last_error && <span className="text-danger">{connection.last_error}</span>}
        </div>
      )}

      {/* EP-26.0.3.1 Part 5 — a richer "Test Connection" result than a
          one-line toast: provider/platform/service identity + capability
          tags, all sourced from the client-side Provider Brand Registry
          (EP-26.0.4) so this needs no new backend call, plus the real
          health/detail the test endpoint already returned. */}
      {lastTestResult && (
        <div
          className={cn(
            "flex flex-col gap-1.5 rounded-lg border p-2.5 ml-5 text-[11px]",
            lastTestResult.health_status === "healthy"
              ? "border-success/30 bg-success-dim/40"
              : "border-danger/30 bg-danger-dim/40",
          )}
        >
          <div className="flex items-center gap-1.5 font-medium text-tx-primary">
            {lastTestResult.health_status === "healthy" ? (
              <CheckCircle2 size={12} className="text-success flex-shrink-0" />
            ) : (
              <XCircle size={12} className="text-danger flex-shrink-0" />
            )}
            {lastTestResult.health_status === "healthy" ? "Connected successfully" : "Connection test failed"}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-tx-muted">
            <span>Provider: {brand.displayName}</span>
            {brand.platform && <span>Platform: {brand.platform}</span>}
            {brand.service && <span>Service: {brand.service}</span>}
            <span>API status: {lastTestResult.tested ? "Reachable" : "Not testable"}</span>
          </div>
          {brand.capabilities.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {brand.capabilities.map((cap) => (
                <span key={cap} className="badge bg-app-muted text-tx-secondary text-[10px]">
                  {cap}
                </span>
              ))}
            </div>
          )}
          <p className="text-tx-secondary">{lastTestResult.detail}</p>
        </div>
      )}

      <SyncStatusPanel organizationId={organizationId} connection={connection} />

      {rotating && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (newKey.trim().length === 0) return;
            rotate.mutate();
          }}
          className="flex flex-col sm:flex-row gap-2 rounded-lg border border-border-subtle bg-app-bg p-2.5 ml-5"
        >
          <ApiKeyInput
            value={newKey}
            onChange={setNewKey}
            disabled={rotate.isPending}
            placeholder="New API key"
            autoFocus
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={rotate.isPending || newKey.trim().length === 0}
              className="btn-primary h-9 px-3 text-xs disabled:opacity-60 inline-flex items-center gap-1.5"
            >
              {rotate.isPending ? <Loader2 size={12} className="animate-spin" /> : <KeyRound size={12} />}
              {rotate.isPending ? "Rotating…" : "Save & validate"}
            </button>
            <button
              type="button"
              onClick={() => {
                setRotating(false);
                setNewKey("");
              }}
              className="btn-ghost h-9 px-3 text-xs"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <ConfirmDialog
        open={confirmingDelete}
        title="Delete this connection?"
        description={`"${connection.display_name}" will be removed. This can't be undone.`}
        confirmLabel="Delete"
        loading={remove.isPending}
        onConfirm={() => {
          remove.mutate(undefined, { onSuccess: () => setConfirmingDelete(false) });
        }}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}

// EP-23.4 — scheduler health/job-status badge colors, mirrors HEALTH_BADGE/
// SYNC_STATUS_BADGE's existing vocabulary rather than inventing a new one.
const SCHEDULER_HEALTH_BADGE: Record<string, { className: string; label: string }> = {
  healthy: { className: "bg-success-dim text-success", label: "Healthy" },
  degraded: { className: "bg-danger-dim text-danger", label: "Degraded" },
  disabled: { className: "bg-app-muted text-tx-muted", label: "Disabled" },
  not_running: { className: "bg-warning-dim text-warning", label: "Not running" },
};

const JOB_STATUS_BADGE: Record<string, { className: string; label: string }> = {
  queued: { className: "bg-app-muted text-tx-muted", label: "Queued" },
  running: { className: "bg-warning-dim text-warning", label: "Running" },
  completed: { className: "bg-success-dim text-success", label: "Completed" },
  failed: { className: "bg-danger-dim text-danger", label: "Failed" },
};

/** EP-23.4 — read-only auto-sync status for the Connections page. The
 * ON/OFF toggle and interval picker live on the Settings page; this panel
 * surfaces what the scheduler is actually doing so users don't have to
 * leave Connections to see whether background sync is working. */
function AutoSyncStatusSection() {
  const organizationId = useOrgStore((s) => s.organizationId);
  const queryClient = useQueryClient();

  const status = useQuery({
    queryKey: ["scheduler-status", organizationId],
    queryFn: () => getSchedulerStatus(organizationId!),
    enabled: !!organizationId,
    // Dashboard refresh requirement (EP-23.4) — poll so a background sync
    // that completes without the user clicking anything is reflected
    // automatically, and refresh the connection list/sync-status queries
    // whenever a job finishes so ConnectionRow/SyncStatusPanel update too.
    refetchInterval: 20_000,
  });

  const [lastSeenJobId, setLastSeenJobId] = useState<string | null>(null);
  const currentJob = status.data?.current_job ?? null;
  useEffect(() => {
    if (!currentJob) return;
    const finished = currentJob.status === "completed" || currentJob.status === "failed";
    if (!finished || currentJob.job_id === lastSeenJobId) return;
    setLastSeenJobId(currentJob.job_id);
    void queryClient.invalidateQueries({ queryKey: ["provider-connections", organizationId] });
    void queryClient.invalidateQueries({
      queryKey: ["provider-connection-sync-status", organizationId],
    });
  }, [currentJob, lastSeenJobId, organizationId, queryClient]);

  if (!status.data) return null;
  const data = status.data;
  const healthBadge =
    SCHEDULER_HEALTH_BADGE[data.scheduler_health] ?? SCHEDULER_HEALTH_BADGE["disabled"]!;

  return (
    <Section title="Automatic sync" description="Background synchronization, configured in Settings." icon={Timer}>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs">
        <div className="flex items-center gap-1.5">
          <span className={cn("badge text-[10px]", data.auto_sync_enabled ? "bg-success-dim text-success" : "bg-app-muted text-tx-muted")}>
            {data.auto_sync_enabled ? "Enabled" : "Disabled"}
          </span>
          {data.auto_sync_enabled && <span className="text-tx-muted">every {data.interval}</span>}
        </div>

        <span className={cn("badge text-[10px]", healthBadge.className)}>
          Scheduler {healthBadge.label.toLowerCase()}
        </span>

        <span className="text-tx-muted inline-flex items-center gap-1">
          <Clock size={12} />
          Last sync {formatValidatedAt(data.last_sync_at) ?? "never"}
        </span>

        {data.auto_sync_enabled && (
          <span className="text-tx-muted inline-flex items-center gap-1">
            <Clock size={12} />
            Next sync {formatValidatedAt(data.next_sync_at) ?? "—"}
          </span>
        )}

        {data.current_job && (
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "badge text-[10px]",
                JOB_STATUS_BADGE[data.current_job.status]?.className ?? "bg-app-muted text-tx-muted",
              )}
            >
              {JOB_STATUS_BADGE[data.current_job.status]?.label ?? data.current_job.status}
            </span>
            <span className="text-tx-muted">
              {formatNumber(data.current_job.records_imported)} records
              {data.current_job.duration_seconds != null &&
                ` · ${data.current_job.duration_seconds.toFixed(1)}s`}
              {data.current_job.retry_count > 0 && ` · retry ${data.current_job.retry_count}`}
            </span>
          </div>
        )}
      </div>
    </Section>
  );
}

function ManageConnectionsSection() {
  const organizationId = useOrgStore((s) => s.organizationId);
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);

  const connections = useQuery({
    queryKey: ["provider-connections", organizationId],
    queryFn: () => listProviderConnections(organizationId!),
    enabled: !!organizationId,
  });

  const list = connections.data?.connections ?? [];

  const syncAll = useMutation({
    mutationFn: () => syncAllProviderConnections(organizationId!),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["provider-connections", organizationId] });
      void queryClient.invalidateQueries({
        queryKey: ["provider-connection-sync-status", organizationId],
      });
      if (result.total === 0) {
        toast.info("Nothing to sync", "No active provider connections yet.");
      } else if (result.failed === 0) {
        toast.success("Sync complete", `Synced ${result.succeeded} of ${result.total} connections.`);
      } else {
        toast.warning(
          "Sync finished with errors",
          `${result.succeeded} of ${result.total} connections synced successfully.`,
        );
      }
    },
    onError: (err: unknown) => {
      toast.error("Couldn't sync connections", err instanceof ApiError ? err.message : "Please try again.");
    },
  });

  return (
    <Section
      title="Your provider connections"
      description="Persisted connections you manage — add, rename, activate/deactivate, test, or remove."
      icon={Plug}
      actions={
        <div className="flex items-center gap-2">
          {list.length > 0 && (
            <button
              onClick={() => syncAll.mutate()}
              disabled={syncAll.isPending}
              className="btn-outline h-8 px-3 text-xs inline-flex items-center gap-1.5 disabled:opacity-60"
            >
              {syncAll.isPending ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
              Sync all
            </button>
          )}
          {!adding && (
            <button onClick={() => setAdding(true)} className="btn-primary h-8 px-3 text-xs inline-flex items-center gap-1.5">
              <Plus size={13} /> Add provider
            </button>
          )}
        </div>
      }
    >
      <div className="space-y-3">
        {adding && organizationId && (
          <AddConnectionForm organizationId={organizationId} onDone={() => setAdding(false)} />
        )}

        {connections.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 2 }, (_, i) => <div key={i} className="h-14 skeleton rounded-xl" />)}
          </div>
        ) : list.length === 0 ? (
          <EmptyState
            icon={Plug}
            title="No provider connections yet"
            description="Add your first connection to start tracking a provider by name, or use the SDK with an API key in the meantime."
            action={
              !adding && organizationId ? (
                <button onClick={() => setAdding(true)} className="btn-primary h-9 px-4 text-sm">
                  Connect provider
                </button>
              ) : undefined
            }
          />
        ) : (
          <div className="space-y-2">
            {list.map((c) => (
              <ConnectionRow key={c.id} organizationId={organizationId!} connection={c} />
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

export default function Connections() {
  return (
    <div className="p-4 sm:p-6 space-y-4 sm:space-y-6">
      <PageHeader
        title="Provider Connections"
        description="Manage persisted connections, verify credentials, and browse live model lists for each adapter."
      />

      <AutoSyncStatusSection />

      <ManageConnectionsSection />

      {/* EP-26.0.3.2 — everything below this point is a separate, internal
          diagnostic surface: it tests Costorah's own server-side
          environment-variable-keyed credentials (an ops/staging probe from
          EP-07), never a customer's own connections managed above. A
          provider can be fully connected, validated, and syncing above
          while still showing here — that's expected, not a contradiction,
          since the two sections check entirely different credentials. */}
      <div className="pt-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-tx-muted mb-1">
          Platform diagnostics
        </p>
        <p className="text-xs text-tx-muted max-w-2xl">
          Internal connectivity checks against Costorah&apos;s own server-side credentials — unrelated
          to the customer connections you manage above.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {PRODUCTION_ADAPTERS.map((p, i) => (
          <ProductionProviderCard key={p} providerId={p} index={i} />
        ))}
      </div>

      <Section
        title="Other adapters (platform diagnostics only)"
        description="These providers don't yet have a server-side ops credential wired up for this internal check. This has no bearing on your own connections above — a provider you've connected and validated can appear here too."
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
              <span className="badge bg-app-muted text-tx-muted text-[9px]">No ops probe</span>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
