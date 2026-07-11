import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2, PanelLeftClose, PanelLeftOpen, Plus, Search } from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import { listPlaygroundHistory } from "../../services/api";
import { CONNECTABLE_PROVIDERS } from "../../lib/providerCatalog";
import { groupByRelativeDay } from "./format";
import { cn } from "../../utils";
import type { PlaygroundExecutionRecord } from "../../services/api";

interface HistorySidebarProps {
  organizationId: string;
  onSelect: (execution: PlaygroundExecutionRecord) => void;
  onNewChat: () => void;
}

/** Redesign goal #6 — a real conversation-history sidebar, browsing the
 * same persisted PlaygroundExecution rows the History tab shows (Costorah
 * has no server-side multi-turn "conversation" entity — see types.ts —
 * so each entry here is one real, past prompt/response exchange, grouped
 * by day like a chat client's history rail). Selecting one loads it into
 * the main conversation pane to review or continue from. */
export default function HistorySidebar({ organizationId, onSelect, onNewChat }: HistorySidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState("");

  const historyQuery = useQuery({
    queryKey: ["playground-history", organizationId, search, provider, "sidebar"],
    queryFn: () =>
      listPlaygroundHistory(organizationId, {
        search: search || undefined,
        provider: provider || undefined,
        limit: 30,
      }),
  });

  if (collapsed) {
    return (
      <div className="hidden lg:flex flex-col items-center gap-2 w-11 flex-shrink-0 pt-1">
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className="p-2 rounded-lg text-tx-muted hover:text-tx-primary hover:bg-app-hover"
          aria-label="Expand chat history"
          title="Expand chat history"
        >
          <PanelLeftOpen size={16} />
        </button>
      </div>
    );
  }

  const groups = groupByRelativeDay(historyQuery.data?.executions ?? []);

  return (
    <div className="flex flex-col gap-2 w-full lg:w-64 flex-shrink-0">
      <div className="glass-card rounded-card-lg border border-border-subtle flex flex-col overflow-hidden max-h-[560px]">
        <div className="flex items-center justify-between gap-2 px-3 py-2.5 border-b border-border-subtle">
          <span className="text-xs font-semibold text-tx-primary">Chat history</span>
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            className="hidden lg:inline-flex p-1 text-tx-muted hover:text-tx-primary"
            aria-label="Collapse chat history"
            title="Collapse chat history"
          >
            <PanelLeftClose size={14} />
          </button>
        </div>

        <div className="p-2.5 flex flex-col gap-2 border-b border-border-subtle">
          <button
            type="button"
            onClick={onNewChat}
            className="btn-outline h-8 text-xs w-full justify-center"
          >
            <Plus size={13} /> New chat
          </button>
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-tx-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search history…"
              aria-label="Search chat history"
              className="w-full rounded-lg border border-border-subtle bg-app-bg pl-7 pr-2 py-1.5 text-xs text-tx-primary outline-none focus:border-brand"
            />
          </div>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            aria-label="Filter chat history by provider"
            className="w-full rounded-lg border border-border-subtle bg-app-bg px-2 py-1.5 text-xs text-tx-primary outline-none focus:border-brand"
          >
            <option value="">All providers</option>
            {CONNECTABLE_PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 overflow-y-auto">
          {historyQuery.isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={16} className="animate-spin text-tx-muted" />
            </div>
          ) : groups.length === 0 ? (
            <p className="text-[11px] text-tx-muted text-center px-3 py-8">
              No past prompts yet — send your first message to start building history here.
            </p>
          ) : (
            groups.map((group) => (
              <div key={group.label}>
                <p className="px-3 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-tx-muted">
                  {group.label}
                </p>
                {group.items.map((execution) => (
                  <button
                    key={execution.id}
                    type="button"
                    onClick={() => onSelect(execution)}
                    className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-app-hover transition-colors"
                  >
                    <ProviderLogo providerId={execution.provider} size="xs" bare />
                    <span className="min-w-0 flex-1">
                      <span className={cn("block text-[11px] truncate", execution.status === "failed" ? "text-danger" : "text-tx-primary")}>
                        {execution.user_prompt}
                      </span>
                      <span className="block text-[10px] text-tx-muted font-mono truncate">{execution.model}</span>
                    </span>
                    <ChevronRight size={11} className="text-tx-muted flex-shrink-0 mt-0.5" />
                  </button>
                ))}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// Mobile toggle helper, exported for the page shell to render a menu
// button above the sidebar on small screens (goal: responsiveness).
export function MobileHistoryToggle({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="lg:hidden btn-ghost h-8 px-2 text-[11px] inline-flex items-center gap-1"
      aria-expanded={open}
    >
      <ChevronLeft size={13} className={cn("transition-transform", open && "rotate-180")} />
      {open ? "Hide history" : "Chat history"}
    </button>
  );
}
