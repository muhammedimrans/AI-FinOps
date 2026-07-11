import { useState } from "react";
import {
  ChevronLeft,
  Copy,
  Download,
  MoreVertical,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { conversationTitle, exportConversationMarkdown, groupConversationsByRecency, type Conversation } from "./conversations";
import { cn } from "../../utils";

// EP-25.4.3 Part 12 — the Chat tab's left rail is now a real ChatGPT-style
// conversation manager: pinned section, Today/Yesterday/This Week/Older
// grouping, search-by-title-or-content, and per-conversation rename/pin/
// duplicate/delete/export — all operating on the local conversation-memory
// layer (conversations.ts's own header comment explains why this is local,
// not a fabricated backend feature). This intentionally supersedes
// EP-25.4.1's version of this component, which browsed individual
// PlaygroundExecution rows directly — that capability (search/filter real,
// individually-persisted requests) still exists, unchanged, on the
// standalone History tab; this sidebar is the conversation-level view.
interface HistorySidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onRename: (id: string, name: string) => void;
  onTogglePin: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string) => void;
}

export default function HistorySidebar({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  onRename,
  onTogglePin,
  onDuplicate,
  onDelete,
}: HistorySidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState("");
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

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

  const query = search.trim().toLowerCase();
  const filtered = query
    ? conversations.filter(
        (c) =>
          conversationTitle(c).toLowerCase().includes(query) ||
          c.turns.some((t) => t.userPrompt.toLowerCase().includes(query)),
      )
    : conversations;
  const groups = groupConversationsByRecency(filtered);

  return (
    <div className="flex flex-col gap-2 w-full lg:w-64 flex-shrink-0">
      <div className="glass-card rounded-card-lg border border-border-subtle flex flex-col overflow-hidden max-h-[560px]">
        <div className="flex items-center justify-between gap-2 px-3 py-2.5 border-b border-border-subtle">
          <span className="text-xs font-semibold text-tx-primary">Conversations</span>
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
          <button type="button" onClick={onNewChat} className="btn-outline h-8 text-xs w-full justify-center">
            <Plus size={13} /> New chat
          </button>
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-tx-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search conversations…"
              aria-label="Search conversations"
              className="w-full rounded-lg border border-border-subtle bg-app-bg pl-7 pr-2 py-1.5 text-xs text-tx-primary outline-none focus:border-brand"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {groups.length === 0 ? (
            <p className="text-[11px] text-tx-muted text-center px-3 py-8">
              No conversations yet — start a new chat to begin building history here.
            </p>
          ) : (
            groups.map((group) => (
              <div key={group.label}>
                <p className="px-3 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-tx-muted">
                  {group.label}
                </p>
                {group.items.map((c) => (
                  <div
                    key={c.id}
                    className={cn(
                      "group relative flex items-center gap-1.5 px-3 py-2 hover:bg-app-hover transition-colors",
                      c.id === activeId && "bg-brand-subtle",
                    )}
                  >
                    {renamingId === c.id ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={() => {
                          if (renameValue.trim()) onRename(c.id, renameValue.trim());
                          setRenamingId(null);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            if (renameValue.trim()) onRename(c.id, renameValue.trim());
                            setRenamingId(null);
                          }
                          if (e.key === "Escape") setRenamingId(null);
                        }}
                        aria-label="Rename conversation"
                        className="flex-1 min-w-0 rounded border border-brand bg-app-bg px-1.5 py-0.5 text-[11px] text-tx-primary outline-none"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => onSelect(c.id)}
                        className="flex-1 min-w-0 text-left"
                      >
                        <span className="flex items-center gap-1 text-[11px] text-tx-primary truncate">
                          {c.pinned && <Pin size={9} className="text-brand flex-shrink-0" />}
                          {conversationTitle(c)}
                        </span>
                        <span className="block text-[10px] text-tx-muted">{c.turns.length} message{c.turns.length === 1 ? "" : "s"}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setMenuFor((prev) => (prev === c.id ? null : c.id))}
                      aria-label={`Conversation options for ${conversationTitle(c)}`}
                      className="p-1 text-tx-muted hover:text-tx-primary opacity-0 group-hover:opacity-100 flex-shrink-0"
                    >
                      <MoreVertical size={13} />
                    </button>
                    {menuFor === c.id && (
                      <div className="absolute right-2 top-8 z-10 w-40 rounded-lg border border-border-subtle bg-app-card shadow-elevated py-1">
                        <MenuItem
                          icon={c.pinned ? PinOff : Pin}
                          label={c.pinned ? "Unpin" : "Pin"}
                          onClick={() => {
                            onTogglePin(c.id);
                            setMenuFor(null);
                          }}
                        />
                        <MenuItem
                          icon={Copy}
                          label="Rename"
                          onClick={() => {
                            setRenamingId(c.id);
                            setRenameValue(conversationTitle(c));
                            setMenuFor(null);
                          }}
                        />
                        <MenuItem
                          icon={Copy}
                          label="Duplicate"
                          onClick={() => {
                            onDuplicate(c.id);
                            setMenuFor(null);
                          }}
                        />
                        <MenuItem
                          icon={Download}
                          label="Export"
                          onClick={() => {
                            const blob = new Blob([exportConversationMarkdown(c)], { type: "text/markdown" });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `costorah-${conversationTitle(c).replace(/\W+/g, "-").toLowerCase() || "conversation"}.md`;
                            a.click();
                            URL.revokeObjectURL(url);
                            setMenuFor(null);
                          }}
                        />
                        <MenuItem
                          icon={Trash2}
                          label="Delete"
                          danger
                          onClick={() => {
                            onDelete(c.id);
                            setMenuFor(null);
                          }}
                        />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function MenuItem({
  icon: Icon,
  label,
  onClick,
  danger,
}: {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full flex items-center gap-2 px-3 py-1.5 text-[11px] text-left hover:bg-app-hover",
        danger ? "text-danger" : "text-tx-secondary",
      )}
    >
      <Icon size={12} /> {label}
    </button>
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
      {open ? "Hide conversations" : "Conversations"}
    </button>
  );
}
