import { Cloud, Code2, FileText, GitCompare, Sparkles, TrendingUp } from "lucide-react";
import ProviderLogo from "../../components/ProviderLogo";
import { getProviderBrand } from "../../lib/providerCatalog";
import { conversationTitle, type Conversation } from "./conversations";
import type { PlaygroundConnectionOption } from "../../services/api";

const SUGGESTED_PROMPTS: { icon: React.ElementType; label: string; prompt: string }[] = [
  { icon: Cloud, label: "Explain Kubernetes", prompt: "Explain Kubernetes to someone who has only used a single VPS." },
  { icon: FileText, label: "Summarize this text", prompt: "Summarize the following text in 3 bullet points:\n\n" },
  { icon: Code2, label: "Generate SQL", prompt: "Write a SQL query that returns the top 10 customers by total spend this year." },
  { icon: Code2, label: "Write Python", prompt: "Write a Python function that deduplicates a list while preserving order." },
  { icon: TrendingUp, label: "Analyze cost", prompt: "Given these token counts and prices, estimate my monthly AI spend:\n\n" },
  { icon: GitCompare, label: "Compare GPT vs Claude", prompt: "Compare GPT-4o and Claude for a customer-support summarization use case." },
];

// EP-25.4.3 Parts 9/16 — the welcome/empty state shown when there's no
// active conversation. Every "Recent conversations" entry is a real, local
// Conversation (conversations.ts); every provider card reflects a real
// PlaygroundConnectionOption this org actually has — never a placeholder
// provider list independent of what's actually connected.
export default function PlaygroundHome({
  connections,
  recentConversations,
  onSuggestedPrompt,
  onOpenConversation,
  onNewChat,
  onGoToConnections,
}: {
  connections: PlaygroundConnectionOption[];
  recentConversations: Conversation[];
  onSuggestedPrompt: (prompt: string) => void;
  onOpenConversation: (id: string) => void;
  onNewChat: () => void;
  onGoToConnections: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-8 py-10 px-4 max-w-3xl mx-auto text-center">
      <div className="flex flex-col items-center gap-3">
        <div className="relative">
          <div className="absolute inset-0 rounded-full blur-xl opacity-40 bg-brand/30" aria-hidden="true" />
          <div className="relative w-14 h-14 rounded-2xl bg-brand-subtle flex items-center justify-center">
            <Sparkles size={24} className="text-brand" />
          </div>
        </div>
        <h2 className="text-xl font-display font-bold text-tx-primary">Welcome to AI Playground</h2>
        <p className="text-sm text-tx-muted max-w-md">
          Test any connected provider, compare responses side by side, and every request becomes real, tracked
          Costorah usage — cost, tokens, latency, budgets, and alerts included.
        </p>
        <button type="button" onClick={onNewChat} className="btn-primary h-9 px-4 text-xs">
          Start a new chat
        </button>
      </div>

      <div className="w-full text-left">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-tx-muted mb-2">Suggested prompts</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {SUGGESTED_PROMPTS.map((s) => (
            <button
              key={s.label}
              type="button"
              onClick={() => onSuggestedPrompt(s.prompt)}
              className="flex items-center gap-2 rounded-lg border border-border-subtle bg-app-muted hover:border-brand/40 hover:bg-app-hover px-3 py-2.5 text-left transition-colors"
            >
              <s.icon size={14} className="text-brand flex-shrink-0" />
              <span className="text-xs text-tx-primary">{s.label}</span>
            </button>
          ))}
        </div>
      </div>

      {connections.length > 0 && (
        <div className="w-full text-left">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-tx-muted mb-2">Your providers</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {connections.map((c) => {
              const brand = getProviderBrand(c.provider_type);
              return (
                <div key={c.id} className="flex items-center gap-2 rounded-lg border border-border-subtle bg-app-muted px-3 py-2">
                  <ProviderLogo providerId={c.provider_type} size="sm" />
                  <div className="min-w-0">
                    <p className="text-xs text-tx-primary truncate">{c.display_name}</p>
                    <p className="text-[10px] text-tx-muted truncate">{brand.displayName}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {connections.length === 0 && (
        <button type="button" onClick={onGoToConnections} className="btn-outline h-9 px-4 text-xs">
          Connect your first provider
        </button>
      )}

      {recentConversations.length > 0 && (
        <div className="w-full text-left">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-tx-muted mb-2">Recent conversations</p>
          <div className="flex flex-col gap-1.5">
            {recentConversations.slice(0, 5).map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => onOpenConversation(c.id)}
                className="flex items-center justify-between rounded-lg border border-border-subtle bg-app-muted hover:bg-app-hover px-3 py-2 text-left transition-colors"
              >
                <span className="text-xs text-tx-primary truncate">{conversationTitle(c)}</span>
                <span className="text-[10px] text-tx-muted flex-shrink-0 ml-2">{c.turns.length} msg</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
