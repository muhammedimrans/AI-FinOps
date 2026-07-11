import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Copy,
  Download,
  Loader2,
  Play,
  RotateCw,
  Search,
  Sparkles,
  Square,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import PageHeader from "../components/PageHeader";
import Section from "../components/Section";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import ProviderLogo from "../components/ProviderLogo";
import {
  listPlaygroundConnections,
  listPlaygroundModels,
  executePlayground,
  comparePlayground,
  listPlaygroundHistory,
  deletePlaygroundExecution,
  rerunPlaygroundExecution,
  listProjectsCrud,
  ApiError,
  type PlaygroundConnectionOption,
  type PlaygroundModelInfo,
  type PlaygroundExecutionRecord,
} from "../services/api";
import { CONNECTABLE_PROVIDERS } from "../lib/providerCatalog";
import { useOrgStore } from "../stores/org";
import { toast } from "../stores/toast";
import { cn, formatNumber } from "../utils";

type Tab = "chat" | "compare" | "history";

interface ConversationTurn {
  id: string;
  connectionId: string;
  providerType: string;
  model: string;
  systemPrompt: string;
  userPrompt: string;
  execution: PlaygroundExecutionRecord | null;
  error: string | null;
  isPending: boolean;
}

/** Minimal markdown-lite renderer for the response window — no new
 * dependency (this app has none for markdown today): handles fenced code
 * blocks, inline code, bold/italic, and paragraph breaks. Genuinely helpful
 * for the common cases an LLM response actually uses without pulling in a
 * full markdown/remark pipeline for one page. */
function renderMarkdownLite(text: string) {
  const blocks = text.split(/```/);
  return blocks.map((block, i) => {
    if (i % 2 === 1) {
      const lines = block.split("\n");
      const lang = lines[0]?.trim();
      const code = lang && !lang.includes(" ") ? lines.slice(1).join("\n") : block;
      return (
        <pre
          key={i}
          className="my-2 overflow-x-auto rounded-lg bg-app-bg border border-border-subtle p-3 text-xs font-mono text-tx-primary"
        >
          <code>{code}</code>
        </pre>
      );
    }
    return block.split(/\n{2,}/).map((para, j) => {
      if (!para.trim()) return null;
      const html = para
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/`([^`]+)`/g, "<code class='px-1 py-0.5 rounded bg-app-bg font-mono text-[0.85em]'>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<em>$1</em>")
        .replace(/\n/g, "<br/>");
      return <p key={`${i}-${j}`} className="mb-2 last:mb-0 leading-relaxed" dangerouslySetInnerHTML={{ __html: html }} />;
    });
  });
}

function CostBadge({ execution }: { execution: PlaygroundExecutionRecord }) {
  if (execution.estimated_cost === null) {
    return (
      <span className="badge bg-app-muted text-tx-muted text-[10px]" title="No pricing configured for this model">
        No pricing
      </span>
    );
  }
  const cost = Number(execution.estimated_cost);
  return (
    <span className="badge bg-brand-subtle text-brand text-[10px] font-mono">
      {cost < 0.01 ? `<$0.01` : `$${cost.toFixed(4)}`} {execution.currency}
    </span>
  );
}

function MetricsRow({ execution }: { execution: PlaygroundExecutionRecord }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-tx-muted font-mono">
      <span>In: {formatNumber(execution.prompt_tokens)}</span>
      <span>Out: {formatNumber(execution.completion_tokens)}</span>
      <span>Total: {formatNumber(execution.total_tokens)}</span>
      {execution.latency_ms !== null && <span>{Math.round(execution.latency_ms)}ms</span>}
      <CostBadge execution={execution} />
    </div>
  );
}

function useConnectionsAndModels(organizationId: string | null) {
  const connectionsQuery = useQuery({
    queryKey: ["playground-connections", organizationId],
    queryFn: () => listPlaygroundConnections(organizationId!),
    enabled: !!organizationId,
  });
  return connectionsQuery;
}

// ── Chat tab ─────────────────────────────────────────────────────────────────

function ChatTab({ organizationId, isPersonal }: { organizationId: string; isPersonal: boolean }) {
  const connectionsQuery = useConnectionsAndModels(organizationId);
  const projectsQuery = useQuery({
    queryKey: ["projects-crud", organizationId],
    queryFn: () => listProjectsCrud(organizationId),
  });

  const connections = connectionsQuery.data?.connections ?? [];
  const configured = connections.filter((c) => c.has_credential || c.provider_type === "ollama");

  const [connectionId, setConnectionId] = useState<string>("");
  const [modelId, setModelId] = useState<string>("");
  const [projectId, setProjectId] = useState<string>("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [userPrompt, setUserPrompt] = useState("");
  const [temperature, setTemperature] = useState(0.7);
  const [topP, setTopP] = useState(1);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);

  const activeConnectionId = connectionId || configured[0]?.id || "";
  const activeConnection = connections.find((c) => c.id === activeConnectionId);

  const modelsQuery = useQuery({
    queryKey: ["playground-models", organizationId, activeConnectionId],
    queryFn: () => listPlaygroundModels(organizationId, activeConnectionId),
    enabled: !!activeConnectionId,
  });
  const models = modelsQuery.data ?? [];
  const activeModelId = modelId || models[0]?.id || "";
  const activeModel = models.find((m) => m.id === activeModelId);

  const execute = useMutation({
    mutationFn: (turnId: string) =>
      executePlayground(organizationId, {
        provider_connection_id: activeConnectionId,
        model_id: activeModelId,
        project_id: projectId || undefined,
        system_prompt: systemPrompt.trim() || undefined,
        user_prompt: userPrompt,
        temperature,
        top_p: topP,
        max_tokens: maxTokens,
      }).then((execution) => ({ turnId, execution })),
    onSuccess: ({ turnId, execution }) => {
      setTurns((prev) =>
        prev.map((t) => (t.id === turnId ? { ...t, execution, isPending: false } : t)),
      );
      if (execution.status === "failed") {
        toast.error("Playground request failed", execution.error_message ?? "The provider returned an error.");
      } else {
        toast.success("Response received", `${formatNumber(execution.total_tokens)} tokens in ${Math.round(execution.latency_ms ?? 0)}ms.`);
      }
    },
    onError: (err: unknown, turnId) => {
      const message = err instanceof ApiError ? err.message : "Please try again.";
      setTurns((prev) => prev.map((t) => (t.id === turnId ? { ...t, error: message, isPending: false } : t)));
      toast.error("Couldn't reach the provider", message);
    },
  });

  function run() {
    if (!activeConnectionId || !activeModelId || !userPrompt.trim()) return;
    const turnId = crypto.randomUUID();
    setTurns((prev) => [
      ...prev,
      {
        id: turnId,
        connectionId: activeConnectionId,
        providerType: activeConnection?.provider_type ?? "",
        model: activeModelId,
        systemPrompt,
        userPrompt,
        execution: null,
        error: null,
        isPending: true,
      },
    ]);
    execute.mutate(turnId);
  }

  function retry(turn: ConversationTurn) {
    setTurns((prev) => prev.map((t) => (t.id === turn.id ? { ...t, isPending: true, error: null } : t)));
    execute.mutate(turn.id);
  }

  function copy(text: string) {
    void navigator.clipboard.writeText(text);
    toast.info("Copied to clipboard");
  }

  function downloadConversation() {
    const lines = turns.map((t) => {
      const header = `## ${t.model} (${t.providerType})\n`;
      const sys = t.systemPrompt ? `**System:** ${t.systemPrompt}\n\n` : "";
      const user = `**Prompt:** ${t.userPrompt}\n\n`;
      const resp = t.execution?.response_text
        ? `**Response:**\n${t.execution.response_text}\n`
        : t.error
          ? `**Error:** ${t.error}\n`
          : "";
      return header + sys + user + resp;
    });
    const blob = new Blob([lines.join("\n---\n\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `costorah-playground-conversation-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (connectionsQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 size={20} className="animate-spin text-tx-muted" />
      </div>
    );
  }

  if (configured.length === 0) {
    return (
      <Section>
        <EmptyState
          icon={Sparkles}
          title="Connect a provider to start"
          description="The Playground sends real requests through your connected providers — connect one (Connections page) to send your first prompt."
          action={
            <a href="/connections" className="btn-primary h-9 px-4 text-xs inline-flex items-center gap-1.5">
              Go to Connections
            </a>
          }
        />
      </Section>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-4">
      <div className="flex flex-col gap-4 min-w-0">
        <Section title="Conversation" bodyClassName="p-0">
          <div className="flex flex-col gap-4 p-4 max-h-[520px] overflow-y-auto">
            {turns.length === 0 ? (
              <p className="text-xs text-tx-muted text-center py-8">
                Send a prompt below — the response, tokens, and cost will appear here, and this
                request becomes real Costorah usage immediately.
              </p>
            ) : (
              <AnimatePresence initial={false}>
                {turns.map((turn) => (
                  <motion.div
                    key={turn.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex flex-col gap-2"
                  >
                    <div className="flex items-start gap-2">
                      <div className="flex-1 min-w-0 rounded-xl bg-app-muted px-3 py-2 text-sm text-tx-primary whitespace-pre-wrap">
                        {turn.userPrompt}
                      </div>
                      <button
                        type="button"
                        onClick={() => copy(turn.userPrompt)}
                        className="p-1.5 text-tx-muted hover:text-tx-primary flex-shrink-0"
                        aria-label="Copy prompt"
                      >
                        <Copy size={13} />
                      </button>
                    </div>

                    <div className="flex items-start gap-2">
                      <div className="flex items-center gap-2 pt-1">
                        <ProviderLogo providerId={turn.providerType} size="sm" />
                      </div>
                      <div className="flex-1 min-w-0 rounded-xl border border-border-subtle bg-app-bg px-3 py-2.5">
                        {turn.isPending ? (
                          <div className="flex items-center gap-2 text-xs text-tx-muted">
                            <Loader2 size={13} className="animate-spin" /> Waiting for response…
                          </div>
                        ) : turn.error ? (
                          <div className="flex flex-col gap-2">
                            <p className="text-xs text-danger">{turn.error}</p>
                            <button
                              type="button"
                              onClick={() => retry(turn)}
                              className="btn-outline h-7 px-2 text-[11px] inline-flex items-center gap-1 self-start"
                            >
                              <RotateCw size={11} /> Retry
                            </button>
                          </div>
                        ) : turn.execution?.status === "failed" ? (
                          <div className="flex flex-col gap-2">
                            <p className="text-xs text-danger">{turn.execution.error_message}</p>
                            <button
                              type="button"
                              onClick={() => retry(turn)}
                              className="btn-outline h-7 px-2 text-[11px] inline-flex items-center gap-1 self-start"
                            >
                              <RotateCw size={11} /> Retry
                            </button>
                          </div>
                        ) : turn.execution ? (
                          <div className="flex flex-col gap-2">
                            <div className="text-sm text-tx-primary">
                              {renderMarkdownLite(turn.execution.response_text ?? "")}
                            </div>
                            <MetricsRow execution={turn.execution} />
                          </div>
                        ) : null}
                      </div>
                      {turn.execution?.response_text && (
                        <button
                          type="button"
                          onClick={() => copy(turn.execution!.response_text!)}
                          className="p-1.5 text-tx-muted hover:text-tx-primary flex-shrink-0"
                          aria-label="Copy response"
                        >
                          <Copy size={13} />
                        </button>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
          </div>

          <div className="border-t border-border-subtle p-4 flex flex-col gap-2">
            <textarea
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              placeholder="Send a message…"
              rows={3}
              className="w-full resize-none rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
            />
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={downloadConversation}
                  disabled={turns.length === 0}
                  className="btn-ghost h-8 px-2 text-[11px] inline-flex items-center gap-1 disabled:opacity-40"
                >
                  <Download size={12} /> Download
                </button>
                <button
                  type="button"
                  onClick={() => setTurns([])}
                  disabled={turns.length === 0}
                  className="btn-ghost h-8 px-2 text-[11px] inline-flex items-center gap-1 disabled:opacity-40"
                >
                  <Trash2 size={12} /> Clear
                </button>
                <button
                  type="button"
                  disabled
                  title="Streaming isn't implemented yet — requests are synchronous, so there's nothing to stop mid-flight."
                  className="btn-ghost h-8 px-2 text-[11px] inline-flex items-center gap-1 opacity-40 cursor-not-allowed"
                >
                  <Square size={12} /> Stop
                </button>
              </div>
              <button
                type="button"
                onClick={run}
                disabled={!userPrompt.trim() || !activeModelId || execute.isPending}
                className="btn-primary h-9 px-4 text-xs disabled:opacity-60 inline-flex items-center gap-1.5"
              >
                {execute.isPending ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                Send
              </button>
            </div>
          </div>
        </Section>
      </div>

      <div className="flex flex-col gap-4">
        <Section title="Provider &amp; model">
          <div className="flex flex-col gap-3">
            <div>
              <label className="text-[11px] text-tx-muted mb-1 block">Provider connection</label>
              <div className="flex items-center gap-2">
                <ProviderLogo providerId={activeConnection?.provider_type ?? ""} size="sm" />
                <select
                  value={activeConnectionId}
                  onChange={(e) => {
                    setConnectionId(e.target.value);
                    setModelId("");
                  }}
                  className="flex-1 rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
                >
                  {connections.map((c) => (
                    <option key={c.id} value={c.id} disabled={!c.has_credential && c.provider_type !== "ollama"}>
                      {c.display_name}
                      {!c.has_credential && c.provider_type !== "ollama" ? " (no credential — connect first)" : ""}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="text-[11px] text-tx-muted mb-1 block">Model</label>
              <select
                value={activeModelId}
                onChange={(e) => setModelId(e.target.value)}
                disabled={modelsQuery.isLoading || models.length === 0}
                className="w-full rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand disabled:opacity-60"
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name}
                    {m.is_deprecated ? " (deprecated)" : ""}
                  </option>
                ))}
              </select>
              {activeModel && (
                <p className="text-[10px] text-tx-muted mt-1">
                  {activeModel.context_window ? `${formatNumber(activeModel.context_window)} ctx` : ""}
                  {activeModel.capabilities.length > 0 ? ` · ${activeModel.capabilities.join(", ")}` : ""}
                </p>
              )}
            </div>

            {!isPersonal && (
              <div>
                <label className="text-[11px] text-tx-muted mb-1 block">Project (optional)</label>
                <select
                  value={projectId}
                  onChange={(e) => setProjectId(e.target.value)}
                  className="w-full rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
                >
                  <option value="">No project</option>
                  {(projectsQuery.data?.projects ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </Section>

        <Section title="Parameters">
          <div className="flex flex-col gap-3">
            <div>
              <label className="flex items-center justify-between text-[11px] text-tx-muted mb-1">
                Temperature <span className="font-mono">{temperature.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="flex items-center justify-between text-[11px] text-tx-muted mb-1">
                Top P <span className="font-mono">{topP.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={topP}
                onChange={(e) => setTopP(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="text-[11px] text-tx-muted mb-1 block">Max tokens</label>
              <input
                type="number"
                min={1}
                max={32000}
                value={maxTokens}
                onChange={(e) => setMaxTokens(Number(e.target.value))}
                className="w-full rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
              />
            </div>
          </div>
        </Section>

        <Section title="System prompt">
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="You are a helpful assistant…"
            rows={4}
            className="w-full resize-none rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
          />
        </Section>
      </div>
    </div>
  );
}

// ── Compare tab ──────────────────────────────────────────────────────────────

type SortKey = "fastest" | "cheapest" | "context" | "lowest_latency";

function CompareTab({ organizationId }: { organizationId: string }) {
  const connectionsQuery = useConnectionsAndModels(organizationId);
  const connections = (connectionsQuery.data?.connections ?? []).filter(
    (c) => c.has_credential || c.provider_type === "ollama",
  );

  const [selected, setSelected] = useState<Record<string, PlaygroundConnectionOption>>({});
  const [modelByConnection, setModelByConnection] = useState<Record<string, string>>({});
  const [userPrompt, setUserPrompt] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [results, setResults] = useState<PlaygroundExecutionRecord[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("fastest");

  const compare = useMutation({
    mutationFn: () => {
      const targets = Object.keys(selected);
      return comparePlayground(organizationId, {
        targets,
        model_ids: modelByConnection,
        system_prompt: systemPrompt.trim() || undefined,
        user_prompt: userPrompt,
      });
    },
    onSuccess: (res) => {
      setResults(res.executions);
      toast.success("Comparison complete", `${res.executions.length} providers responded.`);
    },
    onError: (err: unknown) => {
      toast.error("Comparison failed", err instanceof ApiError ? err.message : "Please try again.");
    },
  });

  const sorted = useMemo(() => {
    const copyArr = [...results];
    switch (sortKey) {
      case "fastest":
        return copyArr.sort((a, b) => (a.latency_ms ?? Infinity) - (b.latency_ms ?? Infinity));
      case "lowest_latency":
        return copyArr.sort((a, b) => (a.latency_ms ?? Infinity) - (b.latency_ms ?? Infinity));
      case "cheapest":
        return copyArr.sort(
          (a, b) => Number(a.estimated_cost ?? Infinity) - Number(b.estimated_cost ?? Infinity),
        );
      case "context":
        return copyArr;
      default:
        return copyArr;
    }
  }, [results, sortKey]);

  if (connections.length < 1) {
    return (
      <Section>
        <EmptyState
          icon={Sparkles}
          title="Connect at least one provider"
          description="Comparison Mode sends the same prompt to several connected providers at once — connect providers first."
        />
      </Section>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Section title="Select providers to compare (up to 8)">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {connections.map((c) => {
            const isSelected = !!selected[c.id];
            return (
              <label
                key={c.id}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer text-sm",
                  isSelected ? "border-brand bg-brand-subtle" : "border-border-subtle bg-app-muted",
                )}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={(e) => {
                    setSelected((prev) => {
                      const next = { ...prev };
                      if (e.target.checked) {
                        if (Object.keys(next).length >= 8) return prev;
                        next[c.id] = c;
                      } else {
                        delete next[c.id];
                      }
                      return next;
                    });
                  }}
                />
                <ProviderLogo providerId={c.provider_type} size="sm" />
                <span className="truncate text-tx-primary">{c.display_name}</span>
              </label>
            );
          })}
        </div>
      </Section>

      {Object.keys(selected).length > 0 && (
        <Section title="Model per provider">
          <div className="flex flex-col gap-2">
            {Object.values(selected).map((c) => (
              <CompareModelRow
                key={c.id}
                organizationId={organizationId}
                connection={c}
                value={modelByConnection[c.id] ?? ""}
                onChange={(modelId) => setModelByConnection((prev) => ({ ...prev, [c.id]: modelId }))}
              />
            ))}
          </div>
        </Section>
      )}

      <Section title="Prompt">
        <div className="flex flex-col gap-2">
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="System prompt (optional)"
            rows={2}
            className="w-full resize-none rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
          />
          <textarea
            value={userPrompt}
            onChange={(e) => setUserPrompt(e.target.value)}
            placeholder="Prompt to send to every selected provider…"
            rows={3}
            className="w-full resize-none rounded-lg border border-border-subtle bg-app-bg px-3 py-2 text-sm text-tx-primary outline-none focus:border-brand"
          />
          <button
            type="button"
            onClick={() => compare.mutate()}
            disabled={
              compare.isPending ||
              !userPrompt.trim() ||
              Object.keys(selected).length === 0 ||
              Object.keys(selected).some((id) => !modelByConnection[id])
            }
            className="btn-primary h-9 px-4 text-xs disabled:opacity-60 inline-flex items-center gap-1.5 self-start"
          >
            {compare.isPending ? <Loader2 size={13} className="animate-spin" /> : <Wand2 size={13} />}
            Run comparison
          </button>
        </div>
      </Section>

      {results.length > 0 && (
        <Section
          title="Results"
          actions={
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="rounded-lg border border-border-subtle bg-app-bg px-2 py-1 text-xs text-tx-primary outline-none focus:border-brand"
            >
              <option value="fastest">Sort: Fastest</option>
              <option value="cheapest">Sort: Cheapest</option>
              <option value="lowest_latency">Sort: Lowest latency</option>
            </select>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] text-tx-muted border-b border-border-subtle">
                  <th className="py-2 pr-3">Provider</th>
                  <th className="py-2 pr-3">Model</th>
                  <th className="py-2 pr-3">Response</th>
                  <th className="py-2 pr-3">Latency</th>
                  <th className="py-2 pr-3">Tokens</th>
                  <th className="py-2 pr-3">Cost</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.id} className="border-b border-border-subtle/60 align-top">
                    <td className="py-2 pr-3">
                      <div className="flex items-center gap-2">
                        <ProviderLogo providerId={r.provider} size="sm" />
                        <span className="text-xs">{r.provider}</span>
                      </div>
                    </td>
                    <td className="py-2 pr-3 text-xs font-mono">{r.model}</td>
                    <td className="py-2 pr-3 max-w-xs text-xs text-tx-primary">
                      {r.status === "failed" ? (
                        <span className="text-danger">{r.error_message}</span>
                      ) : (
                        <span className="line-clamp-3">{r.response_text}</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 text-xs font-mono">
                      {r.latency_ms !== null ? `${Math.round(r.latency_ms)}ms` : "—"}
                    </td>
                    <td className="py-2 pr-3 text-xs font-mono">{formatNumber(r.total_tokens)}</td>
                    <td className="py-2 pr-3">
                      <CostBadge execution={r} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  );
}

function useModelsForConnection(organizationId: string, connectionId: string) {
  return useQuery({
    queryKey: ["playground-models", organizationId, connectionId],
    queryFn: () => listPlaygroundModels(organizationId, connectionId),
    enabled: !!connectionId,
  });
}

function CompareModelRow({
  organizationId,
  connection,
  value,
  onChange,
}: {
  organizationId: string;
  connection: PlaygroundConnectionOption;
  value: string;
  onChange: (modelId: string) => void;
}) {
  const modelsQuery = useModelsForConnection(organizationId, connection.id);
  const models = modelsQuery.data ?? [];
  return (
    <div className="flex items-center gap-2">
      <ProviderLogo providerId={connection.provider_type} size="sm" />
      <span className="text-xs text-tx-secondary w-32 truncate flex-shrink-0">{connection.display_name}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={modelsQuery.isLoading}
        className="flex-1 rounded-lg border border-border-subtle bg-app-bg px-2 py-1.5 text-xs text-tx-primary outline-none focus:border-brand disabled:opacity-60"
      >
        <option value="">Select a model…</option>
        {models.map((m: PlaygroundModelInfo) => (
          <option key={m.id} value={m.id}>
            {m.display_name}
          </option>
        ))}
      </select>
    </div>
  );
}

// ── History tab ──────────────────────────────────────────────────────────────

function HistoryTab({ organizationId }: { organizationId: string }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState("");
  const [pendingDelete, setPendingDelete] = useState<PlaygroundExecutionRecord | null>(null);

  const historyQuery = useQuery({
    queryKey: ["playground-history", organizationId, search, provider],
    queryFn: () =>
      listPlaygroundHistory(organizationId, {
        search: search || undefined,
        provider: provider || undefined,
        limit: 50,
      }),
  });

  const remove = useMutation({
    mutationFn: (executionId: string) => deletePlaygroundExecution(organizationId, executionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["playground-history", organizationId] });
      toast.success("Deleted");
    },
    onError: () => toast.error("Couldn't delete"),
  });

  const rerun = useMutation({
    mutationFn: (executionId: string) => rerunPlaygroundExecution(organizationId, executionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["playground-history", organizationId] });
      toast.success("Re-run complete");
    },
    onError: (err: unknown) =>
      toast.error("Couldn't re-run", err instanceof ApiError ? err.message : "Please try again."),
  });

  function exportHistory() {
    const rows = historyQuery.data?.executions ?? [];
    const csv = [
      "provider,model,status,prompt_tokens,completion_tokens,cost,currency,latency_ms,created_at",
      ...rows.map((r) =>
        [
          r.provider,
          r.model,
          r.status,
          r.prompt_tokens,
          r.completion_tokens,
          r.estimated_cost ?? "",
          r.currency,
          r.latency_ms ?? "",
          r.created_at,
        ].join(","),
      ),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `costorah-playground-history-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const executions = historyQuery.data?.executions ?? [];

  return (
    <Section
      title="Prompt history"
      actions={
        <div className="flex items-center gap-2">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded-lg border border-border-subtle bg-app-bg px-2 py-1.5 text-xs text-tx-primary outline-none focus:border-brand"
          >
            <option value="">All providers</option>
            {CONNECTABLE_PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-tx-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search prompts…"
              className="rounded-lg border border-border-subtle bg-app-bg pl-7 pr-2 py-1.5 text-xs text-tx-primary outline-none focus:border-brand w-40"
            />
          </div>
          <button type="button" onClick={exportHistory} className="btn-ghost h-8 px-2 text-[11px] inline-flex items-center gap-1">
            <Download size={12} /> Export
          </button>
        </div>
      }
    >
      {historyQuery.isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={18} className="animate-spin text-tx-muted" />
        </div>
      ) : executions.length === 0 ? (
        <EmptyState
          title="No Playground history yet"
          description="Every request sent from the Chat or Compare tab appears here — searchable, exportable, and re-runnable."
        />
      ) : (
        <div className="flex flex-col divide-y divide-border-subtle">
          {executions.map((execution) => (
            <div key={execution.id} className="flex items-start gap-3 py-3">
              <ProviderLogo providerId={execution.provider} size="sm" />
              <div className="flex-1 min-w-0">
                <p className="text-xs text-tx-primary truncate">{execution.user_prompt}</p>
                <div className="flex items-center gap-2 mt-1 text-[10px] text-tx-muted">
                  <span className="font-mono">{execution.model}</span>
                  <span>{new Date(execution.created_at).toLocaleString()}</span>
                  {execution.status === "failed" ? (
                    <span className="text-danger">Failed</span>
                  ) : (
                    <span>{formatNumber(execution.total_tokens)} tok</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  type="button"
                  onClick={() => rerun.mutate(execution.id)}
                  disabled={rerun.isPending}
                  className="p-1.5 text-tx-muted hover:text-tx-primary"
                  aria-label="Re-run"
                  title="Re-run this prompt"
                >
                  <RotateCw size={13} />
                </button>
                <button
                  type="button"
                  onClick={() => setPendingDelete(execution)}
                  className="p-1.5 text-tx-muted hover:text-danger"
                  aria-label="Delete"
                >
                  <X size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete this history entry?"
        description="This only removes it from Playground history — it does not affect Analytics, Budgets, or any already-recorded usage."
        confirmLabel="Delete"
        loading={remove.isPending}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id);
          setPendingDelete(null);
        }}
      />
    </Section>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Playground() {
  const organizationId = useOrgStore((s) => s.organizationId);
  const isPersonal = useOrgStore((s) => s.isPersonal);
  const [tab, setTab] = useState<Tab>("chat");

  if (!organizationId) return null;

  const tabs: { key: Tab; label: string }[] = [
    { key: "chat", label: "Chat" },
    { key: "compare", label: "Compare" },
    { key: "history", label: "History" },
  ];

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="AI Playground"
        description="Test connections, compare models, and generate real, tracked Costorah usage — no Postman, no curl."
      />

      <div className="flex items-center gap-1 border-b border-border-subtle">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={cn(
              "px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
              tab === t.key
                ? "border-brand text-tx-primary"
                : "border-transparent text-tx-muted hover:text-tx-secondary",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "chat" && <ChatTab organizationId={organizationId} isPersonal={isPersonal} />}
      {tab === "compare" && <CompareTab organizationId={organizationId} />}
      {tab === "history" && <HistoryTab organizationId={organizationId} />}
    </div>
  );
}
